import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import { AgentEscrow } from "../target/types/agent_escrow";
import { PublicKey, Keypair } from "@solana/web3.js";
import { assert } from "chai";
import * as fs from "fs";

describe("agent_escrow", () => {
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);
  const program = anchor.workspace.AgentEscrow as Program<AgentEscrow>;

  // Platform keypair — the only signer in all instructions (proxy model)
  const platformKpBytes = JSON.parse(fs.readFileSync("/root/platform-keypair.json", "utf-8"));
  const platform = Keypair.fromSecretKey(Uint8Array.from(platformKpBytes));

  // Owner and caller are just pubkeys (not signers in this program)
  const ownerKeypair = Keypair.generate();
  const owner = ownerKeypair.publicKey;
  const caller = ownerKeypair.publicKey; // same for simplicity

  function getAgentPDA(ownerPubkey: PublicKey, slug: string): [PublicKey, number] {
    return PublicKey.findProgramAddressSync(
      [Buffer.from("agent"), ownerPubkey.toBuffer(), Buffer.from(slug)],
      program.programId
    );
  }

  function getExecutionPDA(executionId: number[]): [PublicKey, number] {
    return PublicKey.findProgramAddressSync(
      [Buffer.from("execution"), Buffer.from(executionId)],
      program.programId
    );
  }

  it("registers an agent on-chain", async () => {
    const slug = "test-user/my-agent";
    const pricePerCall = 1_000_000; // 0.001 SOL in lamports

    const [agentPDA] = getAgentPDA(owner, slug);

    await program.methods
      .registerAgent(slug, new anchor.BN(pricePerCall))
      .accountsPartial({
        owner: owner,
        platform: platform.publicKey,
      })
      .signers([platform])
      .rpc();

    const agentAccount = await program.account.agentAccount.fetch(agentPDA);

    assert.equal(agentAccount.owner.toString(), owner.toString());
    assert.equal(agentAccount.slug, slug);
    assert.equal(agentAccount.pricePerCall.toNumber(), pricePerCall);
    assert.equal(agentAccount.reputationScore, 5000);
    assert.equal(agentAccount.totalCalls.toNumber(), 0);
    assert.equal(agentAccount.isActive, true);
  });

  it("rejects price=0 as InvalidPrice", async () => {
    try {
      await program.methods
        .registerAgent("valid-slug", new anchor.BN(0))
        .accountsPartial({
          owner: owner,
          platform: platform.publicKey,
        })
        .signers([platform])
        .rpc();
      assert.fail("Should have thrown");
    } catch (e: any) {
      assert.include(e.message, "InvalidPrice");
    }
  });

  it("initiates an execution and locks SOL in escrow", async () => {
    const slug = "test-user/my-agent";
    const pricePerCall = 1_000_000; // 0.001 SOL
    const [agentPDA] = getAgentPDA(owner, slug);

    const executionId = Array.from(Buffer.from("1234567890abcdef"));
    const [executionPDA] = getExecutionPDA(executionId);

    await program.methods
      .initiateExecution(executionId)
      .accountsPartial({
        agentAccount: agentPDA,
        caller: caller,
        platform: platform.publicKey,
      })
      .signers([platform])
      .rpc();

    const executionAccount = await program.account.executionAccount.fetch(executionPDA);

    assert.equal(executionAccount.caller.toString(), caller.toString());
    assert.equal(executionAccount.agent.toString(), agentPDA.toString());
    assert.equal(executionAccount.amountLocked.toNumber(), pricePerCall);
    assert.deepEqual(executionAccount.status, { pending: {} });
    assert.equal(executionAccount.aiQualityScore, 0);

    const escrowBalance = await provider.connection.getBalance(executionPDA);
    assert.isAtLeast(escrowBalance, pricePerCall);
  });

  it("completes execution — pays agent owner and updates reputation", async () => {
    const slug = "test-user/my-agent";
    const [agentPDA] = getAgentPDA(owner, slug);
    const executionId = Array.from(Buffer.from("complete_exec_01"));
    const [executionPDA] = getExecutionPDA(executionId);

    // First initiate
    await program.methods
      .initiateExecution(executionId)
      .accountsPartial({
        agentAccount: agentPDA,
        caller: caller,
        platform: platform.publicKey,
      })
      .signers([platform])
      .rpc();

    // Complete with AI score 85
    await program.methods
      .completeExecution(85)
      .accountsPartial({
        executionAccount: executionPDA,
        agentAccount: agentPDA,
        agentOwner: owner,
        platformWallet: platform.publicKey,
        platform: platform.publicKey,
      })
      .signers([platform])
      .rpc();

    const executionAccount = await program.account.executionAccount.fetch(executionPDA);
    assert.deepEqual(executionAccount.status, { completed: {} });
    assert.equal(executionAccount.aiQualityScore, 85);

    const agentAccount = await program.account.agentAccount.fetch(agentPDA);
    assert.equal(agentAccount.totalCalls.toNumber(), 1);
    assert.equal(agentAccount.reputationScore, 8500);
  });

  it("refunds execution — returns SOL to caller", async () => {
    const slug = "test-user/my-agent";
    const [agentPDA] = getAgentPDA(owner, slug);
    const executionId = Array.from(Buffer.from("refund_exec_0001"));
    const [executionPDA] = getExecutionPDA(executionId);

    await program.methods
      .initiateExecution(executionId)
      .accountsPartial({
        agentAccount: agentPDA,
        caller: caller,
        platform: platform.publicKey,
      })
      .signers([platform])
      .rpc();

    await program.methods
      .refundExecution()
      .accountsPartial({
        executionAccount: executionPDA,
        caller: caller,
        platform: platform.publicKey,
      })
      .signers([platform])
      .rpc();

    const executionAccount = await program.account.executionAccount.fetch(executionPDA);
    assert.deepEqual(executionAccount.status, { refunded: {} });
  });
});
