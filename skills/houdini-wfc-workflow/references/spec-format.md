# 结构规格与外观catalog

## 目录

- 坐标与结构状态
- 网格、图和约束
- 命令与结果
- 外观变体与适配

## 坐标与结构状态

规格根对象必须有`schema_version: 1`和`modules`，且只能有下表字段；未知字段会报错而不是静默忽略。默认`cell_size=[1,1,1]`、`origin=[0,0,0]`、`pivot_offset=[0.5,0,0.5]`、`seed=0`。

采用Y-up、局部+Z前方。正90° yaw将+X→−Z、+Z→+X。每个模块：

```json
{
  "id": "window",
  "asset_key": "wall_window",
  "weight": 3,
  "tags": ["facade", "glazing"],
  "yaw_variants": [0, 90, 180, 270],
  "sockets": {"px":"wall", "nx":"wall", "py":"up", "ny":"down", "pz":"inside", "nz":"outside"}
}
```

只有`id`和`sockets`必填；`asset_key`默认等于`id`，`weight`默认1，tags默认空，yaw默认`[0]`。权重必须为正数，并在所有yaw间平分。非零yaw需要规范轴向的完整`px/nx/pz/nz`，可选`py/ny`；自定义方向名仅支持yaw 0。每个模块必须给每个声明方向恰好一个socket。

默认方向为`px/nx/py/ny/pz/nz`。可整体替换`directions`；每项包含相反方向和整数delta，例如：

```json
"directions": {
  "px":{"opposite":"nx", "delta":[1,0,0]},
  "nx":{"opposite":"px", "delta":[-1,0,0]}
}
```

默认仅同名socket相连。`socket_pairs:[["a","b"]]`添加对称匹配，不需要同时声明反向对。接口名称是逻辑合同，不会从几何自动学习。

## 网格、图和约束

二选一声明空间：

- `shape:[nx,ny,nz]`创建三维整数网格，可选`active:[[x,y,z],...]`保留活动单元。缺省建立相邻单元的edges。
- `cells:[{"id":"entry","coord":[0,0,0]},...] + edges:[{"a":"entry","direction":"px","b":"hall"}]`创建显式图。此时不自动根据坐标补边；coord可为有限浮点数，selector优先使用唯一id。

单元最终位置为`origin + (coord + pivot_offset) * cell_size`，逐分量计算。外部未连接方向可受`boundary_sockets`约束，例如`{"nx":"outside"}`；活动单元形成的洞边界也属于外部方向。

可选约束：

```json
"constraints": [
  {"cell":[0,0,0], "module":"door", "yaw":90},
  {"cell":"hall", "require_tags":["occupied"], "exclude_tags":["blocked"]}
],
"counts": [
  {"id":"one_entrance", "tags":["entrance"], "min":1, "max":1}
],
"connectivity": {"tags":["road"], "root":[0,0,0], "sockets":["road_open"]},
"budget": {"max_steps":100000, "max_backtracks":10000, "max_seconds":30}
```

`module`使用原型id而不是`id@yaw`。`require_tags`须全部满足，`exclude_tags`命中任一项即排除，空列表不排除。counts对包含全部tags的状态计数，min/max为全局总数。

connectivity选择包含全部tags的单元；指定root时该单元也必须被选中。省略`sockets`只要求这些单元沿图邻边连通；指定非空`sockets`列表后，只有双方对应socket均在列表中且满足邻接匹配才算连通。每个选中单元视为一个内部连通区域，不表达立交内部的分离路线或单向通路。完整赋值后检查，失败会回溯；逻辑连通不是实际净空、碰撞或可达性证明。

`budget`也可由CLI对应选项覆盖，限制求解搜索，不包含读取文件和构建Problem的预处理成本。max_steps和max_backtracks允许0用于验证预算行为，max_seconds必须大于0。

完整可运行示例见`../assets/room-shell.spec.json`：墙、窗、门共享结构接口，转角通过yaw复用，中央floor和边界共同决定布局。

## 命令与结果

```text
wfc.py validate SPEC
wfc.py solve SPEC --output LAYOUT [--seed N] [--max-steps N] [--max-backtracks N] [--max-seconds S] [--force]
wfc.py verify SPEC LAYOUT
wfc.py resolve LAYOUT --catalog CATALOG --style NAME --output INSTANCES [--seed N] [--force]
```

输出父目录必须存在，输出默认独占创建。退出码：0成功；1输入、schema、文件或校验错误；2证明无解；3预算耗尽。求解结果包含规格SHA256、统计、预算和结构cells；成功状态为`solved`。`verify`要求同一规格哈希及全部cells，不接受篡改后只查部分边。

输出cell的`module`是完整状态ID（如`door@90`），`prototype`是原型ID（如`door`），`yaw`独立给角度；输入`constraints.module`用原型ID。`asset_key`用于外观查找，不能把它或状态ID当成原型ID。

## 外观变体与适配

catalog不进入WFC搜索。每个style为每个结构`asset_key`提供至少一个变体：

```json
{
  "schema_version": 1,
  "styles": {
    "brick": {
      "assets": {
        "wall_window": {
          "variants": [{
            "id": "a",
            "asset": "models/brick/window_a.glb",
            "weight": 1,
            "bounds_min": [-1.45, 0, -0.12],
            "bounds_max": [1.45, 2.85, 0.12],
            "anchor": [0, 0, 0],
            "fit": {
              "mode": "axes",
              "target_size": [2.9, 2.85, 0.24],
              "min_scale": [0.97, 0.98, 0.9],
              "max_scale": [1.03, 1.02, 1.1]
            }
          }]
        }
      }
    }
  }
}
```

相对asset路径锚catalog所在目录，解析时必须存在且为文件。bounds是导入并统一单位／朝向后真实局部坐标的总最小／最大值，不是提示词中的设计值。可选成对`fit_bounds_min/fit_bounds_max`表示同一坐标系里实际测得的安装主体包络，必须有序且包含在总bounds内；窗台、檐口等外挑不参与主体尺寸拟合。省略则按总bounds拟合。

anchor是安装基准，可以在几何之外。默认取安装主体的XZ中心、Y最低点；没有fit_bounds时取总bounds。需要把安装面或转角交点放到格点时明确填写anchor，包络拟合不会自动寻找功能面。`fit`：

- `none`：默认，不缩放，且不接受其他fit选项。
- `uniform`：三轴取目标／源尺寸比的最小值。
- `axes`：每轴独立计算比例。

`uniform/axes`必须显式给正数三分量`target_size`，表示源局部轴的安装主体目标尺寸；不从layout的格子大小推断墙厚，也不因yaw交换局部目标轴。`min_scale/max_scale`默认都为`[1,1,1]`，非单位缩放必须明确允许范围；任一轴超限返回`scale_limit`。均匀模式也逐轴核对同一比例，采用包容式拟合，未必填满每个目标轴。单位转换先在源SOP完成，形变容限不代替米／厘米校正。

变体按`sha256(seed + cell_id + asset_key)`确定，与求解RNG分离。`--seed`只覆盖外观seed，不改结构。各风格使用相同variant ID及权重可保持对应槽位；更换style不会重新求解结构。

resolve输出每个实例的`P`、`pivot`、`scale`、`orient`、`piece`、asset路径和world_bounds。world_bounds只包围经过anchor、缩放和旋转后的实测AABB角点，不证明曲面、门窗或接口贴合。

需要严格拼接时，用同源目标尺寸在SOP完成[构件与接口构造](../../houdini-kit-workflow/references/dimensions-and-assembly.md#尺寸来源与接口)，再实测并接入catalog；部件源可以保持原形，通过排列和原生连接结构构成完整模块。已达到安装尺寸的源用`fit.mode=none`，避免二次拉伸。asset、bounds与实际原型应指向同一准备后版本；原始生成文件另行保留。当前schema不存端面轮廓／净空测量，resolver也不会执行局部修形，不向JSON添加未实现的字段冒充几何验证。
