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
        _ctx: Context<RegisterAgent>,
        _slug: String,
        _price_per_call: u64,
    ) -> Result<()> {
        Ok(()) // placeholder — implement in Task 4
    }

    pub fn initiate_execution(
        _ctx: Context<InitiateExecution>,
        _execution_id: [u8; 16],
    ) -> Result<()> {
        Ok(()) // placeholder — implement in Task 5
    }

    pub fn complete_execution(
        _ctx: Context<CompleteExecution>,
        _ai_quality_score: u8,
    ) -> Result<()> {
        Ok(()) // placeholder — implement in Task 6
    }

    pub fn refund_execution(_ctx: Context<RefundExecution>) -> Result<()> {
        Ok(()) // placeholder — implement in Task 6
    }
}

// ─── Context structs (empty for now) ─────────────────────────

#[derive(Accounts)]
pub struct RegisterAgent<'info> {
    #[account(mut)]
    pub owner: Signer<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct InitiateExecution<'info> {
    #[account(mut)]
    pub caller: Signer<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct CompleteExecution<'info> {
    #[account(mut)]
    pub platform: Signer<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct RefundExecution<'info> {
    #[account(mut)]
    pub platform: Signer<'info>,
    pub system_program: Program<'info, System>,
}
