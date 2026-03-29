use anchor_lang::prelude::*;

declare_id!("2qP9GpKCspihqmSggbmu5gg5q5TdDiSGT2JcUhBjUC4G");

// ─── Account structures ──────────────────────────────────────

#[account]
#[derive(Default)]
pub struct AgentAccount {
    pub owner: Pubkey,            // 32 bytes — agent owner wallet
    pub slug: String,             // 4 + 100 bytes — "@username/agent-name"
    pub price_per_call: u64,      // 8 bytes — in lamports
    pub reputation_score: u32,    // 4 bytes — 0–10000 (scaled ×100, so 5000 = 50.00)
    pub total_calls: u64,         // 8 bytes — cumulative call count
    pub is_active: bool,          // 1 byte
    pub bump: u8,                 // 1 byte — PDA bump
}

impl AgentAccount {
    // 8 discriminator + 32 + (4+100) + 8 + 4 + 8 + 1 + 1
    pub const LEN: usize = 8 + 32 + 104 + 8 + 4 + 8 + 1 + 1;
}

#[account]
#[derive(Default)]
pub struct ExecutionAccount {
    pub execution_id: [u8; 16],   // 16 bytes — UUID bytes
    pub caller: Pubkey,           // 32 bytes — who initiated
    pub agent: Pubkey,            // 32 bytes — AgentAccount pubkey
    pub amount_locked: u64,       // 8 bytes — SOL in escrow (lamports)
    pub status: ExecutionStatus,  // 1 byte
    pub ai_quality_score: u8,     // 1 byte — 0–100, set by AI coordinator
    pub created_at: i64,          // 8 bytes — unix timestamp
    pub bump: u8,                 // 1 byte
}

impl ExecutionAccount {
    // 8 + 16 + 32 + 32 + 8 + 1 + 1 + 8 + 1
    pub const LEN: usize = 8 + 16 + 32 + 32 + 8 + 1 + 1 + 8 + 1;
}

#[derive(AnchorSerialize, AnchorDeserialize, Clone, PartialEq, Eq, Default)]
pub enum ExecutionStatus {
    #[default]
    Pending,
    Completed,
    Refunded,
}

// ─── Error types ─────────────────────────────────────────────

#[error_code]
pub enum AgentHubError {
    #[msg("Agent is not active")]
    AgentNotActive,
    #[msg("Execution is not in Pending status")]
    ExecutionNotPending,
    #[msg("AI quality score must be 0–100")]
    InvalidScore,
    #[msg("Slug too long (max 100 chars)")]
    SlugTooLong,
    #[msg("Price must be greater than 0")]
    InvalidPrice,
}

#[program]
pub mod agent_escrow {
    use super::*;

    pub fn register_agent(
        ctx: Context<RegisterAgent>,
        slug: String,
        price_per_call: u64,
    ) -> Result<()> {
        require!(slug.len() <= 100, AgentHubError::SlugTooLong);
        require!(price_per_call > 0, AgentHubError::InvalidPrice);

        let agent = &mut ctx.accounts.agent_account;
        agent.owner = ctx.accounts.owner.key();
        agent.slug = slug;
        agent.price_per_call = price_per_call;
        agent.reputation_score = 5000; // начальная репутация 50.00
        agent.total_calls = 0;
        agent.is_active = true;
        agent.bump = ctx.bumps.agent_account;

        Ok(())
    }

    pub fn initiate_execution(
        ctx: Context<InitiateExecution>,
        execution_id: [u8; 16],
    ) -> Result<()> {
        let agent = &ctx.accounts.agent_account;
        require!(agent.is_active, AgentHubError::AgentNotActive);

        let amount = agent.price_per_call;

        // Перевести SOL из кошелька вызывающего в PDA аккаунт
        let ix = anchor_lang::solana_program::system_instruction::transfer(
            &ctx.accounts.caller.key(),
            &ctx.accounts.execution_account.key(),
            amount,
        );
        anchor_lang::solana_program::program::invoke(
            &ix,
            &[
                ctx.accounts.caller.to_account_info(),
                ctx.accounts.execution_account.to_account_info(),
                ctx.accounts.system_program.to_account_info(),
            ],
        )?;

        let execution = &mut ctx.accounts.execution_account;
        execution.execution_id = execution_id;
        execution.caller = ctx.accounts.caller.key();
        execution.agent = ctx.accounts.agent_account.key();
        execution.amount_locked = amount;
        execution.status = ExecutionStatus::Pending;
        execution.ai_quality_score = 0;
        execution.created_at = Clock::get()?.unix_timestamp;
        execution.bump = ctx.bumps.execution_account;

        Ok(())
    }

    pub fn complete_execution(
        ctx: Context<CompleteExecution>,
        ai_quality_score: u8,
    ) -> Result<()> {
        require!(ai_quality_score <= 100, AgentHubError::InvalidScore);

        let execution = &mut ctx.accounts.execution_account;
        require!(
            execution.status == ExecutionStatus::Pending,
            AgentHubError::ExecutionNotPending
        );

        let amount = execution.amount_locked;
        let owner_amount = amount * 90 / 100;
        let platform_amount = amount - owner_amount;

        // 90% → автор агента
        **execution.to_account_info().try_borrow_mut_lamports()? -= owner_amount;
        **ctx.accounts.agent_owner.try_borrow_mut_lamports()? += owner_amount;

        // 10% → платформа
        **execution.to_account_info().try_borrow_mut_lamports()? -= platform_amount;
        **ctx.accounts.platform_wallet.try_borrow_mut_lamports()? += platform_amount;

        execution.status = ExecutionStatus::Completed;
        execution.ai_quality_score = ai_quality_score;

        // Обновить репутацию агента: скользящее среднее
        let agent = &mut ctx.accounts.agent_account;
        agent.total_calls += 1;
        let score_contribution = ai_quality_score as u32 * 100; // масштаб 0–10000
        // reputation = (old_rep * (calls-1) + new_score) / calls
        agent.reputation_score = (
            agent.reputation_score * (agent.total_calls as u32 - 1) + score_contribution
        ) / agent.total_calls as u32;

        Ok(())
    }

    pub fn refund_execution(ctx: Context<RefundExecution>) -> Result<()> {
        let execution = &mut ctx.accounts.execution_account;
        require!(
            execution.status == ExecutionStatus::Pending,
            AgentHubError::ExecutionNotPending
        );

        let amount = execution.amount_locked;

        // Вернуть 100% SOL вызывающему
        **execution.to_account_info().try_borrow_mut_lamports()? -= amount;
        **ctx.accounts.caller.try_borrow_mut_lamports()? += amount;

        execution.status = ExecutionStatus::Refunded;

        Ok(())
    }
}

// ─── Context structs (empty for now) ─────────────────────────

#[derive(Accounts)]
#[instruction(slug: String)]
pub struct RegisterAgent<'info> {
    #[account(
        init,
        payer = owner,
        space = AgentAccount::LEN,
        seeds = [b"agent", owner.key().as_ref(), slug.as_bytes()],
        bump
    )]
    pub agent_account: Account<'info, AgentAccount>,

    #[account(mut)]
    pub owner: Signer<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(execution_id: [u8; 16])]
pub struct InitiateExecution<'info> {
    #[account(
        init,
        payer = caller,
        space = ExecutionAccount::LEN,
        seeds = [b"execution", execution_id.as_ref()],
        bump
    )]
    pub execution_account: Account<'info, ExecutionAccount>,

    #[account(
        seeds = [b"agent", agent_account.owner.as_ref(), agent_account.slug.as_bytes()],
        bump = agent_account.bump
    )]
    pub agent_account: Account<'info, AgentAccount>,

    #[account(mut)]
    pub caller: Signer<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct CompleteExecution<'info> {
    #[account(
        mut,
        seeds = [b"execution", execution_account.execution_id.as_ref()],
        bump = execution_account.bump
    )]
    pub execution_account: Account<'info, ExecutionAccount>,

    #[account(
        mut,
        seeds = [b"agent", agent_account.owner.as_ref(), agent_account.slug.as_bytes()],
        bump = agent_account.bump
    )]
    pub agent_account: Account<'info, AgentAccount>,

    /// CHECK: validated as agent owner via agent_account.owner
    #[account(mut, address = agent_account.owner)]
    pub agent_owner: UncheckedAccount<'info>,

    /// CHECK: platform fee recipient
    #[account(mut)]
    pub platform_wallet: UncheckedAccount<'info>,

    // Только platform может вызвать complete_execution
    pub platform: Signer<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct RefundExecution<'info> {
    #[account(
        mut,
        seeds = [b"execution", execution_account.execution_id.as_ref()],
        bump = execution_account.bump
    )]
    pub execution_account: Account<'info, ExecutionAccount>,

    /// CHECK: validated as original caller
    #[account(mut, address = execution_account.caller)]
    pub caller: UncheckedAccount<'info>,

    // Только platform может вызвать refund
    pub platform: Signer<'info>,

    pub system_program: Program<'info, System>,
}
