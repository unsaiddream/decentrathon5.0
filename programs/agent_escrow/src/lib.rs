use anchor_lang::prelude::*;

declare_id!("6jbMUjdDJZTha1XWy2Zr3GDki7zS2dxUdm5snWyJL5SZ");

#[program]
pub mod agent_escrow {
    use super::*;

    pub fn initialize(ctx: Context<Initialize>) -> Result<()> {
        msg!("Greetings from: {:?}", ctx.program_id);
        Ok(())
    }
}

#[derive(Accounts)]
pub struct Initialize {}
