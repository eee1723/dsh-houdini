# 按需动词输入与返回契约

> 自动生成，勿手改。唯一维护源：[verb-operation-contracts.json](../houdini/verb-operation-contracts.json)。
> 生成：`npm run docs:generate`；漂移检查：`npm run docs:check`。

## 使用方式与维护范围

模型通过 `verb_help("build_module")` 或名称列表按需查询；不把本页全部内容拼入常驻提示。
`signature`、`return_type`、`call_mode` 和 `doc` 从真实函数取得。已维护的动词还返回 `operation_contract`，
包含输入和返回字段、可执行 Python 示例、结果读取方式及接口边界。其他动词仍使用运行时签名与说明。

JSON Schema subsets describe serializable arguments and successful verb-ledger result projections. Additional properties remain open unless the actual nested input spec is closed. Runtime signature/doc remains authoritative; these schemas are discovery metadata, not dispatch validation.

All Python examples run inside one Houdini exec/inspect request. Live hou.Node values and Python locals are scoped to that request. Persist explicit path strings in __result__ and use those strings in later requests; ledger {node:path} snapshots are observations, not callable Node objects.

JSON Schema是描述字段结构的格式。这里维护可序列化输入与成功动词回执的结构子集，开放未枚举的返回字段；
它不在执行时验证请求，不增加流程、审批或执行门槛。失败继续使用真实异常、动词回执及恢复事实。
函数签名/默认值不在JSON重复维护；节点参数、菜单与默认值由 `node_info` 或实际节点参数查询取得。

实现：[按需运行时帮助](../houdini/python3.11libs/dsh_execution.py)、[Houdini动词](../houdini/python3.11libs/dsh_hou_helpers.py)。
验证：[模块与帮助边界](../tools/tests/dsh-module-boundaries.test.py)、[生成器](../tools/gen-verb-contract-docs.mjs)。

## 已维护目录

- [verb_help](#verb_help)
- [node_info](#node_info)
- [tab_create](#tab_create)
- [build_module](#build_module)
- [verify_network](#verify_network)
- [set_parms](#set_parms)
- [connect](#connect)
- [network_boxes](#network_boxes)
- [cook_node](#cook_node)
- [geo_piece_stats](#geo_piece_stats)
- [create_spare_parms](#create_spare_parms)
- [sop_set_output](#sop_set_output)
- [render_view](#render_view)
- [scene_save](#scene_save)

## verb_help

Discover actual callable signatures and the available on-demand argument/result contracts.

### 输入结构

```json
{
  "type": "object",
  "properties": {
    "name": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "array",
          "items": {
            "type": "string"
          },
          "minItems": 1,
          "maxItems": 16,
          "uniqueItems": true
        }
      ]
    }
  },
  "required": [
    "name"
  ],
  "additionalProperties": true
}
```

### 成功动词回执的返回结构

```json
{
  "anyOf": [
    {
      "type": "object",
      "properties": {
        "name": {
          "type": "string"
        },
        "signature": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ]
        },
        "return_type": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ]
        },
        "call_mode": {
          "type": "string"
        },
        "doc": {
          "type": "string"
        },
        "operation_contract": {
          "type": "object"
        }
      },
      "required": [
        "name",
        "signature",
        "return_type",
        "call_mode",
        "doc"
      ],
      "additionalProperties": true
    },
    {
      "type": "object",
      "properties": {
        "items": {
          "type": "array",
          "items": {
            "type": "object"
          }
        },
        "count": {
          "type": "integer"
        }
      },
      "required": [
        "items",
        "count"
      ],
      "additionalProperties": true
    }
  ]
}
```

### Inspect a focused group

调用工具：`houdini_inspect`。

```python
__result__ = verb_help(['build_module', 'network_boxes', 'node_info', 'tab_create'])
```

items contains one actual signature per name; operation_contract is present where documented.

### 接口边界

- List input returns items/count, not a mapping keyed by verb name. Other verbs still supply runtime signature, return_type, call_mode and doc.
- call_mode=exec means houdini_exec or houdini_job_submit; query_or_exec is also available through houdini_inspect. Python names, live Node objects and local variables do not persist across separate tool calls.

## node_info

Read static node type and parameter templates in a real creation network without creating a probe.

### 输入结构

```json
{
  "type": "object",
  "properties": {
    "parent": {
      "type": "string",
      "description": "Existing absolute node path. Within the same exec a live hou.Node is also accepted; JSON node snapshots are not hou.Node objects."
    },
    "type_name": {
      "type": "string"
    },
    "parm_filter": {
      "type": "string"
    },
    "limit": {
      "type": "integer"
    }
  },
  "required": [
    "parent",
    "type_name"
  ],
  "additionalProperties": true
}
```

### 成功动词回执的返回结构

```json
{
  "type": "object",
  "properties": {
    "parent": {
      "type": "string"
    },
    "type": {
      "type": "string"
    },
    "category": {
      "type": "string"
    },
    "parameters": {
      "type": "array",
      "items": {
        "type": "object"
      }
    },
    "parameter_count": {
      "type": "integer"
    },
    "total_parameter_count": {
      "type": "integer"
    },
    "operation_parameters": {
      "type": "array",
      "items": {
        "type": "object"
      }
    },
    "operation_card": {
      "type": "object"
    },
    "truncated": {
      "type": "boolean"
    },
    "filter_mode": {
      "type": "string"
    }
  },
  "required": [
    "parent",
    "type",
    "category",
    "parameters",
    "parameter_count",
    "total_parameter_count",
    "truncated"
  ],
  "additionalProperties": true
}
```

### Discover Box SOP after creating its container

调用工具：`houdini_exec`。

```python
geo = tab_create('/obj', 'geo', name='example_geo')
__result__ = node_info(geo, 'box', parm_filter='size')
```

Read parameters (not parms or setting_cards); operation_parameters, when present, remains unfiltered.

### Query an existing SOP network

调用工具：`houdini_inspect`。

```python
__result__ = node_info('/obj/example_geo', 'box', parm_filter='', limit=64)
```

This query requires example_geo to exist; /obj creates OBJ nodes and cannot supply a Box SOP card.

### 接口边界

- parm_filter is a literal substring, not regex, glob or a pipe-separated list. Static defaults and menus do not describe shelf initialization or dynamic menus on a live node.

## tab_create

Create and initialize one node, then optionally wire inputs and set strict parameters.

### 输入结构

```json
{
  "type": "object",
  "properties": {
    "parent": {
      "type": "string",
      "description": "Existing absolute node path. Within the same exec a live hou.Node is also accepted; JSON node snapshots are not hou.Node objects."
    },
    "type_name": {
      "type": "string"
    },
    "name": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ]
    },
    "inputs": {
      "anyOf": [
        {
          "type": "array",
          "items": {
            "anyOf": [
              {
                "type": "string",
                "description": "Existing node path, absolute or relative to the explicit parent; a live hou.Node is also accepted within the same exec."
              },
              {
                "type": "null"
              }
            ]
          }
        },
        {
          "type": "null"
        }
      ]
    },
    "parms": {
      "anyOf": [
        {
          "type": "object",
          "minProperties": 1
        },
        {
          "type": "null"
        }
      ]
    }
  },
  "required": [
    "parent",
    "type_name"
  ],
  "additionalProperties": true
}
```

### 成功动词回执的返回结构

```json
{
  "anyOf": [
    {
      "type": "object",
      "properties": {
        "node": {
          "type": "string"
        }
      },
      "required": [
        "node"
      ],
      "additionalProperties": true
    },
    {
      "type": "null"
    }
  ]
}
```

### Use a live Node immediately and return a reusable path

调用工具：`houdini_exec`。

```python
geo = tab_create('/obj', 'geo', name='example_geo')
box = tab_create(geo, 'box', name='box1')
set_parms(box, {'sizex': 2.0})
__result__ = {'geo_path': geo.path(), 'box_path': box.path()}
```

Python returns a live hou.Node. The verb ledger projects it as {node: path}; __result__ explicitly returns path strings for a later tool call.

### Preserve an empty first input

调用工具：`houdini_exec`。

```python
node = tab_create('/obj/example_geo', 'attribwrangle', name='lookup', inputs=[None, 'box1'])
__result__ = node.path()
```

box1 must already exist inside example_geo. None leaves input 0 empty and wires box1 to input 1.

### 接口边界

- A successful Python return is a Node, not a dict with ok/created. Do not pass the ledger snapshot {node: path} back as a Node; use its path string.
- Input references are resolved relative to parent; cross-network dataflow requires explicit subnet ports or Object Merge. OBJ parenting uses set_object_parent.

## build_module

Build a new editable SOP batch with explicit node specs and a nonempty output.

### 输入结构

```json
{
  "type": "object",
  "properties": {
    "parent": {
      "type": "string",
      "description": "Existing absolute node path. Within the same exec a live hou.Node is also accepted; JSON node snapshots are not hou.Node objects."
    },
    "nodes": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string"
          },
          "type": {
            "type": "string"
          },
          "parms": {
            "type": "object"
          },
          "inputs": {
            "type": "array",
            "items": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ]
            }
          }
        },
        "required": [
          "name",
          "type"
        ],
        "additionalProperties": false
      },
      "minItems": 1
    },
    "output": {
      "type": "string"
    },
    "dry_run": {
      "type": "boolean"
    },
    "interfaces": {
      "anyOf": [
        {
          "type": "array",
          "items": {
            "type": "object"
          }
        },
        {
          "type": "null"
        }
      ]
    },
    "required_outputs": {
      "anyOf": [
        {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        {
          "type": "null"
        }
      ]
    }
  },
  "required": [
    "parent",
    "nodes",
    "output"
  ],
  "additionalProperties": true
}
```

### 成功动词回执的返回结构

```json
{
  "anyOf": [
    {
      "type": "object",
      "properties": {
        "valid": {
          "const": true
        },
        "dry_run": {
          "const": true
        },
        "parent": {
          "type": "string"
        },
        "node_count": {
          "type": "integer"
        },
        "output": {
          "type": "string"
        },
        "scene_writes": {
          "const": 0
        },
        "applied": {
          "const": false
        },
        "interface_status": {
          "type": "string"
        }
      },
      "required": [
        "valid",
        "dry_run",
        "parent",
        "node_count",
        "output",
        "scene_writes",
        "applied"
      ],
      "additionalProperties": true
    },
    {
      "type": "object",
      "properties": {
        "valid": {
          "const": true
        },
        "dry_run": {
          "const": false
        },
        "parent": {
          "type": "string"
        },
        "created": {
          "type": "object",
          "additionalProperties": {
            "type": "string"
          }
        },
        "validation": {
          "type": "object"
        },
        "interface_checks": {
          "type": "object"
        }
      },
      "required": [
        "valid",
        "dry_run",
        "parent",
        "created",
        "validation"
      ],
      "additionalProperties": true
    }
  ]
}
```

### Build and retain the real output path

调用工具：`houdini_exec`。

```python
r = build_module('/obj/example_geo', [
    {'name': 'source', 'type': 'box', 'parms': {'sizex': 2.0}},
    {'name': 'OUT', 'type': 'null', 'inputs': ['source']},
], output='OUT')
__result__ = {'output_path': r['created']['OUT'], 'validation': r['validation']}
```

On applied success read created[name] and validation. There is no top-level ok or output in this applied return.

### Preview without creating nodes

调用工具：`houdini_exec`。

```python
__result__ = build_module('/obj/example_geo', [
    {'name': 'OUT_preview', 'type': 'null', 'inputs': ['box1']},
], output='OUT_preview', dry_run=True)
```

dry_run returns node_count/output/valid and zero writes; it does not return created/validation or prove VEX/cook/geometry.

### 接口边界

- nodes entries accept exactly name/type/parms/inputs; no comment, flags or position field. References may name any declared spec or an existing direct child; declaration order does not control wiring.
- None retains an input slot. output and required_outputs name newly declared nodes. Empty controls/helpers can be created separately with tab_create; dry-run cannot prove the resulting geometry.

## verify_network

Cook a declared SOP scope and report actual output content, errors and warnings.

### 输入结构

```json
{
  "type": "object",
  "properties": {
    "parent": {
      "type": "string",
      "description": "Existing absolute node path. Within the same exec a live hou.Node is also accepted; JSON node snapshots are not hou.Node objects."
    },
    "output": {
      "type": "string",
      "description": "Existing node path, absolute or relative to the explicit parent; a live hou.Node is also accepted within the same exec."
    },
    "nodes": {
      "anyOf": [
        {
          "type": "array",
          "items": {
            "type": "string",
            "description": "Existing node path, absolute or relative to the explicit parent; a live hou.Node is also accepted within the same exec."
          }
        },
        {
          "type": "null"
        }
      ]
    },
    "limit": {
      "type": "integer"
    },
    "require_valid": {
      "type": "boolean"
    },
    "output_index": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ]
    }
  },
  "required": [
    "parent",
    "output"
  ],
  "additionalProperties": true
}
```

### 成功动词回执的返回结构

```json
{
  "type": "object",
  "properties": {
    "ok": {
      "type": "boolean"
    },
    "output": {
      "type": "string"
    },
    "parent": {
      "type": "string"
    },
    "scope": {
      "type": "string"
    },
    "checked_nodes": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "node_count": {
      "type": "integer"
    },
    "nonempty": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ]
    },
    "healthy": {
      "type": "boolean"
    },
    "warning_free": {
      "type": "boolean"
    },
    "error_nodes": {
      "type": "array",
      "items": {
        "type": "object"
      }
    },
    "warning_nodes": {
      "type": "array",
      "items": {
        "type": "object"
      }
    },
    "geometry": {
      "anyOf": [
        {
          "type": "object"
        },
        {
          "type": "null"
        }
      ]
    },
    "semantic_status": {
      "type": "string"
    },
    "failure_reasons": {
      "type": "array",
      "items": {
        "type": "string"
      }
    }
  },
  "required": [
    "ok",
    "output",
    "parent",
    "scope",
    "node_count",
    "nonempty",
    "healthy",
    "warning_free"
  ],
  "additionalProperties": true
}
```

### Verify the explicit output

调用工具：`houdini_exec`。

```python
__result__ = verify_network('/obj/example_geo', output='OUT', nodes=['source', 'OUT'])
```

Read output, checked_nodes, nonempty, error_nodes and warning_nodes. Paths may be parent-relative.

### Read a failed checkpoint diagnostically

调用工具：`houdini_exec`。

```python
__result__ = verify_network('/obj/example_geo', output='OUT', require_valid=False)
```

require_valid=False returns diagnostic facts, including ok=False; it does not turn errors or an empty output into success.

### 接口边界

- output must be explicit; omission never selects displayNode. Default scope is direct children, explicit nodes limits it. Cook/content checks do not prove relationships or visual quality.

## set_parms

Apply a strict parameter batch to one node, preserving actual errors and restoring snapshotted parameter state on failure.

### 输入结构

```json
{
  "type": "object",
  "properties": {
    "node": {
      "type": "string",
      "description": "Existing absolute node path. Within the same exec a live hou.Node is also accepted; JSON node snapshots are not hou.Node objects."
    },
    "values": {
      "type": "object",
      "minProperties": 1,
      "description": "Parameter or tuple names to literal values, numeric expressions, explicit expression/language objects, or supported literal string patches."
    },
    "allow_foreign": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ]
    },
    "strict": {
      "type": "boolean"
    }
  },
  "required": [
    "node",
    "values"
  ],
  "additionalProperties": true
}
```

### 成功动词回执的返回结构

```json
{
  "type": "object",
  "properties": {
    "node": {
      "type": "string"
    },
    "ok": {
      "type": "boolean"
    },
    "set": {
      "type": "object"
    },
    "failed": {
      "type": "object"
    },
    "evaluations": {
      "type": "object"
    },
    "effect_status": {
      "type": "string"
    },
    "notes": {
      "type": "object"
    }
  },
  "required": [
    "node",
    "ok",
    "set"
  ],
  "additionalProperties": true
}
```

### Use exact parameter names and explicit expressions

调用工具：`houdini_exec`。

```python
__result__ = set_parms('/obj/example_geo/box1', {
    'sizex': 2.0,
    'sizey': {'expression': 'ch("sizex") * 0.5', 'language': 'hscript'},
})
```

Read set/evaluations. A parameter write does not itself certify downstream geometry; cook or verify that output when needed.

### 接口边界

- Parameter names and menu set_value come from node_info/list_parms/read_parms. Numeric tuple literals use full components; tuple expressions use individual component names.
- strict defaults to True. strict=False allows explicit partial diagnostic success and returns failed; it is not required for ordinary editing. Restoration covers parameter values/expressions/keys, not external callback effects.

## connect

Connect exact source/output and destination/input ports in the same dataflow network.

### 输入结构

```json
{
  "type": "object",
  "properties": {
    "src": {
      "type": "string",
      "description": "Existing absolute node path. Within the same exec a live hou.Node is also accepted; JSON node snapshots are not hou.Node objects."
    },
    "dst": {
      "type": "string",
      "description": "Existing absolute node path. Within the same exec a live hou.Node is also accepted; JSON node snapshots are not hou.Node objects."
    },
    "index": {
      "type": [
        "integer",
        "string"
      ]
    },
    "output": {
      "type": [
        "integer",
        "string"
      ]
    },
    "allow_foreign": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ]
    }
  },
  "required": [
    "src",
    "dst"
  ],
  "additionalProperties": true
}
```

### 成功动词回执的返回结构

```json
{
  "type": "object",
  "properties": {
    "node": {
      "type": "string"
    },
    "source": {
      "type": "string"
    },
    "input": {
      "type": "integer"
    },
    "source_output": {
      "type": "integer"
    },
    "verified": {
      "type": "boolean"
    },
    "position_adjusted": {
      "type": "boolean"
    },
    "placement_status": {
      "type": "string"
    },
    "inputs_after": {
      "type": "object",
      "properties": {
        "connections": {
          "type": "array",
          "items": {
            "type": "object"
          }
        },
        "count": {
          "type": "integer"
        },
        "truncated": {
          "type": "boolean"
        }
      },
      "required": [
        "connections",
        "count",
        "truncated"
      ],
      "additionalProperties": true
    }
  },
  "required": [
    "node",
    "source",
    "input",
    "source_output",
    "verified",
    "position_adjusted",
    "placement_status"
  ],
  "additionalProperties": true
}
```

### Replace one wire without a separate disconnect

调用工具：`houdini_exec`。

```python
__result__ = connect('/obj/example_geo/source', '/obj/example_geo/OUT', index=0, output=0)
```

node is the destination; input/source_output report the actual ports and inputs_after shows the current wiring.

### 接口边界

- output is keyword-only. Port strings are exact port names, not labels. connect replaces the current occupant; OBJ parenting is a separate set_object_parent operation.

## network_boxes

Create, update or remove presentation groups without moving or cooking nodes.

### 输入结构

```json
{
  "type": "object",
  "properties": {
    "parent": {
      "type": "string",
      "description": "Existing absolute node path. Within the same exec a live hou.Node is also accepted; JSON node snapshots are not hou.Node objects."
    },
    "groups": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string"
          },
          "members": {
            "type": "array",
            "items": {
              "type": "string",
              "description": "Existing node path, absolute or relative to the explicit parent; a live hou.Node is also accepted within the same exec."
            }
          },
          "boxes": {
            "type": "array",
            "items": {
              "type": "string"
            }
          },
          "label": {
            "type": "string"
          },
          "role": {
            "type": [
              "string",
              "null"
            ]
          },
          "color": {
            "type": "array",
            "items": {
              "type": "number"
            },
            "minItems": 3,
            "maxItems": 3
          }
        },
        "required": [
          "name"
        ],
        "additionalProperties": false
      }
    },
    "remove": {
      "anyOf": [
        {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        {
          "type": "null"
        }
      ]
    },
    "dry_run": {
      "type": "boolean"
    },
    "expected_plan": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ]
    },
    "allow_foreign": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ]
    }
  },
  "required": [
    "parent",
    "groups"
  ],
  "additionalProperties": true
}
```

### 成功动词回执的返回结构

```json
{
  "type": "object",
  "properties": {
    "ok": {
      "type": "boolean"
    },
    "dry_run": {
      "type": "boolean"
    },
    "applied": {
      "type": "boolean"
    },
    "scene_writes": {
      "type": "integer"
    },
    "phase": {
      "type": "string"
    },
    "parent": {
      "type": "string"
    },
    "plan_sha256": {
      "type": "string"
    },
    "boxes": {
      "type": "array",
      "items": {
        "type": "object"
      }
    },
    "created": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "updated": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "removed": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "unchanged": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "layout_status": {
      "type": "string"
    }
  },
  "required": [
    "ok",
    "dry_run",
    "applied",
    "scene_writes",
    "phase",
    "parent",
    "plan_sha256",
    "boxes",
    "layout_status"
  ],
  "additionalProperties": true
}
```

### Apply a simple group directly

调用工具：`houdini_exec`。

```python
__result__ = network_boxes('/obj/example_geo', [
    {'name': 'shape', 'members': ['source', 'OUT'], 'label': 'Shape'},
])
```

Direct application is supported. Read boxes and created/updated/unchanged; there is no native box_count field.

### Declare a container before its child

调用工具：`houdini_exec`。

```python
__result__ = network_boxes('/obj/example_geo', [
    {'name': 'assembly', 'boxes': ['shape'], 'role': 'component'},
    {'name': 'shape', 'members': ['source', 'OUT'], 'role': 'model'},
], dry_run=True)
```

The preview resolves same-call box names regardless of declaration order; it writes nothing. To pin this preview, pass expected_plan=preview[plan_sha256] on the applying call.

### 接口边界

- members and boxes may coexist. label defaults to name; role is an optional color hint and is not a fixed enum or leaf/component gate. Containment cycles are rejected.
- expected_plan is optional; preview plus hash is useful when a caller chooses to require unchanged presentation state. Grouping reports presentation, not geometry correctness.

## cook_node

Evaluate one node and report cook health without treating warnings or Manual mode as success.

### 输入结构

```json
{
  "type": "object",
  "properties": {
    "node": {
      "type": "string",
      "description": "Existing absolute node path. Within the same exec a live hou.Node is also accepted; JSON node snapshots are not hou.Node objects."
    },
    "force": {
      "type": "boolean"
    },
    "timeout_ms": {
      "type": "integer"
    }
  },
  "required": [
    "node"
  ],
  "additionalProperties": true
}
```

### 成功动词回执的返回结构

```json
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string"
    },
    "ok": {
      "type": "boolean"
    },
    "healthy": {
      "type": "boolean"
    },
    "warning_free": {
      "type": "boolean"
    },
    "errors": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "warnings": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "forced": {
      "type": "boolean"
    },
    "status": {
      "type": "string"
    }
  },
  "required": [
    "path",
    "ok",
    "healthy",
    "warning_free",
    "errors",
    "warnings",
    "forced"
  ],
  "additionalProperties": true
}
```

### Read actual cook health

调用工具：`houdini_exec`。

```python
__result__ = cook_node('/obj/example_geo/OUT', force=True)
```

path identifies the node. ok covers errors; healthy also requires no warnings. Manual mode reports not_cooked_manual.

### 接口边界

- timeout_ms is cooperative native interruption, not an immediate kill. A successful cook does not assert nonempty geometry or visual quality.

## geo_piece_stats

Observe connected-piece geometry or bounded Polygon surface integrity without modifying the source network.

### 输入结构

```json
{
  "type": "object",
  "properties": {
    "node": {
      "type": "string",
      "description": "Existing absolute node path. Within the same exec a live hou.Node is also accepted; JSON node snapshots are not hou.Node objects."
    },
    "piece_attrib": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ]
    },
    "sample": {
      "type": "integer"
    },
    "inspect": {
      "type": "boolean"
    },
    "group": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ]
    },
    "basis": {
      "anyOf": [
        {
          "type": "array",
          "items": {
            "type": "array",
            "items": {
              "type": "number"
            },
            "minItems": 3,
            "maxItems": 3
          },
          "minItems": 3,
          "maxItems": 3
        },
        {
          "type": "null"
        }
      ]
    },
    "integrity_only": {
      "type": "boolean"
    }
  },
  "required": [
    "node"
  ],
  "additionalProperties": true
}
```

### 成功动词回执的返回结构

```json
{
  "anyOf": [
    {
      "type": "object",
      "properties": {
        "node": {
          "type": "string"
        },
        "piece_count": {
          "type": "integer"
        },
        "piece_attrib": {
          "type": "string"
        },
        "piece_attrib_class": {
          "type": "string"
        },
        "sampled_pieces": {
          "type": "array",
          "items": {
            "type": "object"
          }
        },
        "degenerate_surface_pieces": {
          "type": "integer"
        }
      },
      "required": [
        "node",
        "piece_count",
        "sampled_pieces"
      ],
      "additionalProperties": true
    },
    {
      "type": "object",
      "properties": {
        "node": {
          "type": "string"
        },
        "frame": {
          "type": "number"
        },
        "status": {
          "type": "string"
        },
        "scope": {
          "type": "string"
        },
        "semantic_status": {
          "type": "string"
        },
        "risk_status": {
          "type": "string"
        }
      },
      "required": [
        "node",
        "frame",
        "status",
        "semantic_status"
      ],
      "additionalProperties": true
    }
  ]
}
```

### Observe connected pieces

调用工具：`houdini_inspect`。

```python
__result__ = geo_piece_stats('/obj/example_geo/OUT', sample=16)
```

Read piece_count and sampled_pieces. Their extents/area are observations, not proof that parts meet each other.

### Inspect supported Polygon integrity

调用工具：`houdini_inspect`。

```python
__result__ = geo_piece_stats('/obj/example_geo/OUT', inspect=True, integrity_only=True)
```

Read status, supported/unverified scope and risk_status; planar_face_crossings supplies its own coverage/skipped counts. These are not a product-quality pass.

### 接口边界

- group/basis require inspect=True; integrity_only also requires inspect=True. Default piece statistics and Polygon inspection return different shapes; unsupported geometry remains unverified.

## create_spare_parms

Create editable parameter controls on one node by explicit scalar specs, code references, or the parameter UI layout vocabulary.

### 输入结构

```json
{
  "type": "object",
  "properties": {
    "node": {
      "type": "string",
      "description": "Existing absolute node path. Within the same exec a live hou.Node is also accepted; JSON node snapshots are not hou.Node objects."
    },
    "code_parm": {
      "type": "string"
    },
    "defaults": {
      "anyOf": [
        {
          "type": "object"
        },
        {
          "type": "null"
        }
      ]
    },
    "spec": {
      "anyOf": [
        {
          "type": "array",
          "items": {
            "type": "object"
          }
        },
        {
          "type": "null"
        }
      ]
    },
    "allow_foreign": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ]
    },
    "update_defaults": {
      "anyOf": [
        {
          "type": "object"
        },
        {
          "type": "null"
        }
      ]
    },
    "layout": {
      "anyOf": [
        {
          "type": "array",
          "items": {
            "type": "object"
          }
        },
        {
          "type": "null"
        }
      ]
    },
    "dry_run": {
      "type": "boolean"
    }
  },
  "required": [
    "node"
  ],
  "additionalProperties": true
}
```

### 成功动词回执的返回结构

```json
{
  "type": "object",
  "properties": {
    "node": {
      "type": "string"
    },
    "mode": {
      "type": "string"
    },
    "created": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "leaf_values": {
      "type": "object"
    },
    "code_parm": {
      "type": "string"
    },
    "references": {
      "type": "object",
      "additionalProperties": {
        "type": "string"
      }
    },
    "existing": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "unsupported": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "refreshed_code_parm": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ]
    }
  },
  "required": [
    "node"
  ],
  "additionalProperties": true
}
```

### Add a scalar control explicitly

调用工具：`houdini_exec`。

```python
__result__ = create_spare_parms('/obj/example_geo/CTRL', spec=[
    {'type': 'float', 'name': 'width', 'label': 'Width', 'default': 2.0, 'min': 0.1, 'max': 10.0},
])
```

CTRL must exist. Explicit spec returns node/mode/created/leaf_values; it does not return the scanned-reference shape.

### 接口边界

- Simplified spec supports recursive folders and toggle/int/float/string scalars. Use verb_help(hda_set_interface) for the complete layout vocabulary; do not mix layout fields into simplified spec.
- layout is exclusive with spec/defaults/update_defaults; dry_run is available in layout mode. update_defaults changes existing spare defaults and preserves current values/keys.

## sop_set_output

Set the explicit SOP display/render output for the user and optionally publish a native subnet Output port.

### 输入结构

```json
{
  "type": "object",
  "properties": {
    "node": {
      "type": "string",
      "description": "Existing absolute node path. Within the same exec a live hou.Node is also accepted; JSON node snapshots are not hou.Node objects."
    },
    "render": {
      "type": "boolean"
    },
    "allow_foreign": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ]
    },
    "output_index": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ]
    }
  },
  "required": [
    "node"
  ],
  "additionalProperties": true
}
```

### 成功动词回执的返回结构

```json
{
  "type": "object",
  "properties": {
    "context": {
      "const": "sop"
    },
    "node": {
      "type": "string"
    },
    "display": {
      "type": "boolean"
    },
    "render": {
      "type": "boolean"
    },
    "source": {
      "type": "string"
    },
    "public_output": {
      "anyOf": [
        {
          "type": "object"
        },
        {
          "type": "null"
        }
      ]
    }
  },
  "required": [
    "context",
    "node",
    "display",
    "render",
    "source",
    "public_output"
  ],
  "additionalProperties": true
}
```

### Make the chosen SOP visible

调用工具：`houdini_exec`。

```python
__result__ = sop_set_output('/obj/example_geo/OUT')
```

Read node/source/display/render. A named Null alone is not a public subnet port; an explicit output_index requests that publication.

### 接口边界

- This changes the user output flag and is separate from offscreen render_view, which uses an explicit target. It does not verify geometry or infer deliverable quality.

## render_view

Render an explicit SOP through the Houdini GUI preview service and return real image, framing and pixel observations.

### 输入结构

```json
{
  "type": "object",
  "properties": {
    "node": {
      "type": "string",
      "description": "Existing absolute node path. Within the same exec a live hou.Node is also accepted; JSON node snapshots are not hou.Node objects."
    },
    "direction": {
      "anyOf": [
        {
          "type": "string",
          "enum": [
            "iso",
            "front",
            "side",
            "top"
          ]
        },
        {
          "type": "array",
          "items": {
            "type": "number"
          },
          "minItems": 3,
          "maxItems": 3
        }
      ]
    },
    "frame": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ]
    },
    "width": {
      "type": "integer"
    },
    "height": {
      "type": "integer"
    },
    "picture": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ]
    },
    "framing": {
      "type": "string",
      "enum": [
        "full",
        "detail"
      ]
    },
    "coverage": {
      "type": "number"
    },
    "framing_frame": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ]
    },
    "output_policy": {
      "type": "string",
      "enum": [
        "managed",
        "explicit"
      ]
    },
    "focus_group": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ]
    },
    "isolate": {
      "type": "boolean"
    },
    "projection": {
      "type": "string",
      "enum": [
        "perspective",
        "orthographic"
      ]
    },
    "framing_bounds": {
      "anyOf": [
        {
          "type": "array",
          "items": {
            "type": "array",
            "items": {
              "type": "number"
            },
            "minItems": 3,
            "maxItems": 3
          },
          "minItems": 2,
          "maxItems": 2
        },
        {
          "type": "null"
        }
      ]
    },
    "depth_bounds": {
      "anyOf": [
        {
          "type": "array",
          "items": {
            "type": "array",
            "items": {
              "type": "number"
            },
            "minItems": 3,
            "maxItems": 3
          },
          "minItems": 2,
          "maxItems": 2
        },
        {
          "type": "null"
        }
      ]
    }
  },
  "required": [
    "node"
  ],
  "additionalProperties": true
}
```

### 成功动词回执的返回结构

```json
{
  "type": "object",
  "properties": {
    "ok": {
      "type": "boolean"
    },
    "errors": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "output": {
      "type": "string"
    },
    "artifact": {
      "type": "object"
    },
    "framing": {
      "type": "object"
    },
    "check": {
      "anyOf": [
        {
          "type": "object"
        },
        {
          "type": "null"
        }
      ]
    },
    "pixels": {
      "anyOf": [
        {
          "type": "object"
        },
        {
          "type": "null"
        }
      ]
    },
    "stale": {
      "type": "boolean"
    },
    "semantic_status": {
      "type": "string"
    },
    "user_state_restored": {
      "type": "boolean"
    }
  },
  "required": [
    "ok",
    "errors",
    "output",
    "framing",
    "check",
    "pixels",
    "stale"
  ],
  "additionalProperties": true
}
```

### Produce a managed observation image

调用工具：`houdini_exec`。

```python
__result__ = render_view('/obj/example_geo/OUT', direction='iso', width=1280, height=720, picture='shape_iso.png')
```

Read output/artifact and errors, framing, check, stale. The returned image is sent through the Host to the model; the model still needs to inspect it.

### 接口边界

- Requires the GUI preview service; headless renderer checks use render_frame. Managed outputs are under $HIP/dsh-visual-checks; explicit destinations require output_policy=explicit.
- A/B observations use the same framing_frame, direction, framing.bounds and framing.depth_bounds. Pixels and file delivery do not certify visual semantics.

## scene_save

Save the current named HIP and report actual filesystem and dirty-state facts.

### 输入结构

```json
{
  "type": "object",
  "properties": {
    "expected_path": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ]
    }
  },
  "required": [],
  "additionalProperties": true
}
```

### 成功动词回执的返回结构

```json
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string"
    },
    "dirty_before": {
      "type": "boolean"
    },
    "dirty_after": {
      "type": "boolean"
    },
    "dirty_reliable": {
      "type": "boolean"
    },
    "clean_on_disk": {
      "anyOf": [
        {
          "type": "boolean"
        },
        {
          "type": "null"
        }
      ]
    },
    "bytes": {
      "type": "integer"
    },
    "mtime_ns": {
      "type": "integer"
    }
  },
  "required": [
    "path",
    "dirty_before",
    "dirty_after",
    "dirty_reliable",
    "clean_on_disk",
    "bytes",
    "mtime_ns"
  ],
  "additionalProperties": true
}
```

### Save the current named scene

调用工具：`houdini_exec`。

```python
__result__ = scene_save(expected_path=scene_info()['hip_path'])
```

Read path and bytes; clean_on_disk can be None when GUI dirty state is unavailable. An unnamed scene needs explicit scene_save_as instead.

### 接口边界

- scene_save does not perform Save As, load or clear. expected_path is optional but, when given, must match the actual current HIP.
