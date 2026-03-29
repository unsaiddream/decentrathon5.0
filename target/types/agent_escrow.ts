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
          "name": "caller",
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
          "name": "owner",
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
