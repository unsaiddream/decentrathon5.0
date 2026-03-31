/**
 * Program IDL in camelCase format in order to be used in JS/TS.
 *
 * Note that this is only a type helper and is not the actual IDL. The original
 * IDL can be found at `target/idl/agent_escrow.json`.
 */
export type AgentEscrow = {
  "address": "2qP9GpKCspihqmSggbmu5gg5q5TdDiSGT2JcUhBjUC4G",
  "metadata": {
    "name": "agentEscrow",
    "version": "0.1.0",
    "spec": "0.1.0",
    "description": "Created with Anchor"
  },
  "instructions": [
    {
      "name": "completeExecution",
      "docs": [
        "Завершение выполнения — AI координатор одобрил качество.",
        "90% SOL → agent owner, 10% → platform. Репутация обновляется."
      ],
      "discriminator": [
        55,
        101,
        52,
        4,
        121,
        233,
        150,
        50
      ],
      "accounts": [
        {
          "name": "executionAccount",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  101,
                  120,
                  101,
                  99,
                  117,
                  116,
                  105,
                  111,
                  110
                ]
              },
              {
                "kind": "account",
                "path": "execution_account.execution_id",
                "account": "executionAccount"
              }
            ]
          }
        },
        {
          "name": "agentAccount",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  97,
                  103,
                  101,
                  110,
                  116
                ]
              },
              {
                "kind": "account",
                "path": "agent_account.owner",
                "account": "agentAccount"
              },
              {
                "kind": "account",
                "path": "agent_account.slug",
                "account": "agentAccount"
              }
            ]
          }
        },
        {
          "name": "agentOwner",
          "writable": true
        },
        {
          "name": "platformWallet",
          "writable": true
        },
        {
          "name": "platform",
          "docs": [
            "Only platform can call complete_execution"
          ],
          "signer": true
        },
        {
          "name": "systemProgram",
          "address": "11111111111111111111111111111111"
        }
      ],
      "args": [
        {
          "name": "aiQualityScore",
          "type": "u8"
        }
      ]
    },
    {
      "name": "initiateExecution",
      "docs": [
        "Инициация выполнения — platform фиксирует SOL в PDA эскроу.",
        "Caller pubkey сохраняется для возврата при refund."
      ],
      "discriminator": [
        38,
        226,
        189,
        251,
        242,
        163,
        232,
        209
      ],
      "accounts": [
        {
          "name": "executionAccount",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  101,
                  120,
                  101,
                  99,
                  117,
                  116,
                  105,
                  111,
                  110
                ]
              },
              {
                "kind": "arg",
                "path": "executionId"
              }
            ]
          }
        },
        {
          "name": "agentAccount",
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  97,
                  103,
                  101,
                  110,
                  116
                ]
              },
              {
                "kind": "account",
                "path": "agent_account.owner",
                "account": "agentAccount"
              },
              {
                "kind": "account",
                "path": "agent_account.slug",
                "account": "agentAccount"
              }
            ]
          }
        },
        {
          "name": "caller"
        },
        {
          "name": "platform",
          "docs": [
            "Platform signs and provides SOL for escrow"
          ],
          "writable": true,
          "signer": true
        },
        {
          "name": "systemProgram",
          "address": "11111111111111111111111111111111"
        }
      ],
      "args": [
        {
          "name": "executionId",
          "type": {
            "array": [
              "u8",
              16
            ]
          }
        }
      ]
    },
    {
      "name": "refundExecution",
      "docs": [
        "Возврат средств — AI координатор отклонил качество или таймаут.",
        "100% SOL возвращается caller."
      ],
      "discriminator": [
        210,
        43,
        26,
        214,
        125,
        234,
        204,
        229
      ],
      "accounts": [
        {
          "name": "executionAccount",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  101,
                  120,
                  101,
                  99,
                  117,
                  116,
                  105,
                  111,
                  110
                ]
              },
              {
                "kind": "account",
                "path": "execution_account.execution_id",
                "account": "executionAccount"
              }
            ]
          }
        },
        {
          "name": "caller",
          "writable": true
        },
        {
          "name": "platform",
          "docs": [
            "Only platform can call refund_execution"
          ],
          "signer": true
        },
        {
          "name": "systemProgram",
          "address": "11111111111111111111111111111111"
        }
      ],
      "args": []
    },
    {
      "name": "registerAgent",
      "docs": [
        "Регистрация агента — platform подписывает как proxy за owner.",
        "Owner pubkey хранится в AgentAccount и используется для PDA seeds."
      ],
      "discriminator": [
        135,
        157,
        66,
        195,
        2,
        113,
        175,
        30
      ],
      "accounts": [
        {
          "name": "agentAccount",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  97,
                  103,
                  101,
                  110,
                  116
                ]
              },
              {
                "kind": "account",
                "path": "owner"
              },
              {
                "kind": "arg",
                "path": "slug"
              }
            ]
          }
        },
        {
          "name": "owner"
        },
        {
          "name": "platform",
          "docs": [
            "Platform signs and pays for account creation (proxy for owner)"
          ],
          "writable": true,
          "signer": true
        },
        {
          "name": "systemProgram",
          "address": "11111111111111111111111111111111"
        }
      ],
      "args": [
        {
          "name": "slug",
          "type": "string"
        },
        {
          "name": "pricePerCall",
          "type": "u64"
        }
      ]
    },
    {
      "name": "updateReputation",
      "docs": [
        "Обновление репутации агента — вызывается platform отдельно.",
        "Можно вызывать независимо от complete_execution для ручных корректировок."
      ],
      "discriminator": [
        194,
        220,
        43,
        201,
        54,
        209,
        49,
        178
      ],
      "accounts": [
        {
          "name": "agentAccount",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  97,
                  103,
                  101,
                  110,
                  116
                ]
              },
              {
                "kind": "account",
                "path": "agent_account.owner",
                "account": "agentAccount"
              },
              {
                "kind": "account",
                "path": "agent_account.slug",
                "account": "agentAccount"
              }
            ]
          }
        },
        {
          "name": "platform",
          "docs": [
            "Only platform can update reputation"
          ],
          "signer": true
        }
      ],
      "args": [
        {
          "name": "newScoreContribution",
          "type": "u32"
        }
      ]
    }
  ],
  "accounts": [
    {
      "name": "agentAccount",
      "discriminator": [
        241,
        119,
        69,
        140,
        233,
        9,
        112,
        50
      ]
    },
    {
      "name": "executionAccount",
      "discriminator": [
        99,
        155,
        10,
        60,
        111,
        133,
        18,
        99
      ]
    }
  ],
  "errors": [
    {
      "code": 6000,
      "name": "agentNotActive",
      "msg": "Agent is not active"
    },
    {
      "code": 6001,
      "name": "executionNotPending",
      "msg": "Execution is not in Pending status"
    },
    {
      "code": 6002,
      "name": "invalidScore",
      "msg": "AI quality score must be 0–100"
    },
    {
      "code": 6003,
      "name": "slugTooLong",
      "msg": "Slug too long (max 100 chars)"
    },
    {
      "code": 6004,
      "name": "invalidPrice",
      "msg": "Price must be greater than 0"
    }
  ],
  "types": [
    {
      "name": "agentAccount",
      "type": {
        "kind": "struct",
        "fields": [
          {
            "name": "owner",
            "type": "pubkey"
          },
          {
            "name": "slug",
            "type": "string"
          },
          {
            "name": "pricePerCall",
            "type": "u64"
          },
          {
            "name": "reputationScore",
            "type": "u32"
          },
          {
            "name": "totalCalls",
            "type": "u64"
          },
          {
            "name": "isActive",
            "type": "bool"
          },
          {
            "name": "bump",
            "type": "u8"
          }
        ]
      }
    },
    {
      "name": "executionAccount",
      "type": {
        "kind": "struct",
        "fields": [
          {
            "name": "executionId",
            "type": {
              "array": [
                "u8",
                16
              ]
            }
          },
          {
            "name": "caller",
            "type": "pubkey"
          },
          {
            "name": "agent",
            "type": "pubkey"
          },
          {
            "name": "amountLocked",
            "type": "u64"
          },
          {
            "name": "status",
            "type": {
              "defined": {
                "name": "executionStatus"
              }
            }
          },
          {
            "name": "aiQualityScore",
            "type": "u8"
          },
          {
            "name": "createdAt",
            "type": "i64"
          },
          {
            "name": "bump",
            "type": "u8"
          }
        ]
      }
    },
    {
      "name": "executionStatus",
      "type": {
        "kind": "enum",
        "variants": [
          {
            "name": "pending"
          },
          {
            "name": "completed"
          },
          {
            "name": "refunded"
          }
        ]
      }
    }
  ]
};
