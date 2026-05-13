# 智能路线规划系统

一个基于 FastAPI 的智能路线规划原型，支持多城市出行场景。系统使用本地 JSON 数据完成意图解析、POI 召回、路线生成、二次规划和中文解释生成，提供命令行工具和 API 接口两种测试方式。

支持城市：北京、上海、广州、深圳、成都、杭州、武汉、西安、重庆、南京、天津、苏州、长沙、青岛、郑州、厦门、昆明、大连、三亚、丽江。

## 目录结构

```text
route_planner/
├── cli.py                    # 命令行测试工具
├── app.py                    # FastAPI 入口，API 路由定义
├── generate_poi_data.py      # 数据生成脚本（10万条 POI + 评论）
├── data/
│   ├── poi_data_100k.json    # 多城市 POI 数据（10万条）
│   ├── reviews_100k.json     # UGC 评论数据（约45万条）
│   ├── pois.json             # 精选 POI 样例（40条，成都）
│   ├── reviews.json          # 精选评论样例（40条）
│   └── user_profiles.json    # 用户画像数据（6种类型）
├── core/
│   ├── intent_parser.py      # 用户意图解析
│   ├── poi_retriever.py      # POI 召回与评分
│   ├── ugc_analyzer.py       # UGC 评论分析
│   ├── scorer.py             # 评分计算
│   ├── route_optimizer.py    # 路线优化（Beam Search）
│   ├── replanner.py          # 重新规划
│   ├── explanation.py        # 中文解释生成
│   └── preference.py         # 偏好匹配工具
├── models/
│   ├── schemas.py            # 数据模型（Pydantic）
│   └── config.py             # 配置文件
├── utils/
│   ├── geo.py                # 地理距离计算
│   └── time_utils.py         # 时间工具
├── tests/
│   └── test_e2e.py           # 端到端测试（7个用例）
├── requirements.txt
└── README.md
```

## 环境准备

```bash
conda create -n rounter python=3.12 -y
conda activate rounter
pip install -r requirements.txt
```

## 生成数据

首次使用需生成 10 万条模拟数据：

```bash
python generate_poi_data.py
```

生成文件位于 `data/` 目录：
- `poi_data_100k.json`（约 125 MB）：20 个城市，100,000 条 POI
- `reviews_100k.json`（约 131 MB）：约 450,000 条用户评论

## 命令行工具（推荐）

### 查看用户画像

```bash
python cli.py profiles
```

输出：

```text
  u001  文艺慢逛型    预算260元/天  偏好: 书店, 茶馆, 安静, 文艺
  u002  亲子轻松型    预算320元/天  偏好: 亲子, 室内, 雨天友好, 短停留
  u003  拍照打卡型    预算380元/天  偏好: 拍照, 夜景, 城市地标, 建筑
  u004  夜游朋友局    预算450元/天  偏好: 夜景, 夜宵, 酒吧, 音乐
  u005  本地美食优先  预算300元/天  偏好: 火锅, 串串, 小吃, 本地味道
  u006  文化家庭游    预算360元/天  偏好: 文化, 历史, 亲子, 公园
```

### 规划路线

```bash
# 使用默认用户（u001 文艺慢逛型）
python cli.py plan "下午从春熙路出发，想吃火锅、拍照，不想排队，预算300，晚上9点前结束"

# 指定用户画像
python cli.py plan "下午想吃火锅，预算300" --user u005
python cli.py plan "带孩子出去玩，预算300" --user u002
python cli.py plan "晚上和朋友喝酒看夜景" --user u004
```

执行后自动保存用户和意图到 `.last_intent.json`，重新规划时自动沿用。

### 重新规划

基于上次规划结果，输入反馈即可重新生成路线：

```bash
python cli.py replan "太贵了，控制在100以内"
python cli.py replan "不要火锅了，换成小吃"
python cli.py replan "下雨了，安排室内"
python cli.py replan "晚点出发，下午3点开始"
python cli.py replan "少走路，别太累"
```

### 查看数据概览

```bash
python cli.py pois
```

### 查看帮助

```bash
python cli.py -h
```

## 命令行输出示例

### 规划结果

输入：

```bash
python cli.py plan "下午从春熙路出发，想吃火锅、拍照，预算300"
```

输出（explanation 部分）：

```text
已根据你的需求生成路线建议。

【识别到的需求】
城市：成都；起点：春熙路；时间：14:00 至 21:00；预算：300元以内；偏好：想吃火锅、重视拍照出片。

【路线推荐】
 综合最优路线（综合评分 0.8603）
    预算：约119元（含交通费32.8元） |  总耗时：约351分钟
    行程：
      1. 14:18→古涮肉坊 （打车18分钟（30.2），停留163分钟，人均28，排队约17分钟）
      2. 17:34→徐火锅 （地铁/公交16分钟（2.3），停留73分钟，人均20，排队约26分钟）
      3. 19:15→奢华音乐厅 （地铁/公交2分钟（0.3），停留22分钟，人均38，排队约14分钟）
    推荐：整体POI质量较高；预算可控；路线比较紧凑；品类较丰富；包含餐饮补给。
    提示：暂无明显风险，按当前时间和预算约束可正常执行。

 少排队优先路线（综合评分 0.8364）
    预算：约278元（含交通费43.7元） |  总耗时：约376分钟
    行程：
      1. 14:28→孙火锅城 （打车28分钟（42.8），停留134分钟，人均123，排队约20分钟）
      2. 17:06→徐火锅 （步行4分钟，停留73分钟，人均20，排队约26分钟）
      3. 18:47→奢华音乐厅 （地铁/公交2分钟（0.3），停留22分钟，人均38，排队约14分钟）
      4. 19:28→月亮船少年宫 （地铁/公交5分钟（0.6），停留34分钟，人均53，排队约14分钟）

 低预算优先路线（综合评分 0.8582）
    预算：约134元（含交通费33.0元） |  总耗时：约365分钟
    行程：
      1. 14:18→古涮肉坊 （打车18分钟（30.2），停留163分钟，人均28，排队约17分钟）
      2. 17:34→徐火锅 （地铁/公交16分钟（2.3），停留73分钟，人均20，排队约26分钟）
      3. 19:17→月亮船少年宫 （地铁/公交4分钟（0.5），停留34分钟，人均53，排队约14分钟）

【可调整建议】
- 如果想更稳，可以提高预算或减少高客单价餐饮点。
- 如果遇到下雨，可以补充"雨天"或"室内"，系统会优先选择商场、书店、茶馆等点位。
```

### 重新规划结果

输入：

```bash
python cli.py replan "太贵了，控制在100以内"
```

输出（intent 部分）：

```json
{
  "city": "成都",
  "start_location": "春熙路",
  "start_time": "14:00",
  "end_time": "21:00",
  "budget": 100,
  "preferences": ["火锅", "拍照"],
  "avoid": [],
  "travel_mode": "walking",
  "people_count": 1,
  "scenario": "general"
}
```

## API 接口

如需通过 HTTP 接口测试，可启动 FastAPI 服务：

```bash
uvicorn app:app --reload
```

启动后访问 Swagger UI：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 启动检查

```bash
curl http://127.0.0.1:8000/start
```

### 查看用户画像

```bash
curl http://127.0.0.1:8000/profiles
```

### 查看 POI 数据概览

```bash
curl http://127.0.0.1:8000/pois
```

### 生成路线

```bash
curl -X POST http://127.0.0.1:8000/plan \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u001","query":"下午从春熙路出发，想吃火锅、拍照，预算300"}'
```

### 重新规划

```bash
curl -X POST http://127.0.0.1:8000/replan \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u001","previous_intent":{...},"feedback":"太贵了，控制在150以内"}'
```

## 运行测试

```bash
pytest tests/ -v
```

7 个端到端测试用例：
1. 火锅偏好路线包含火锅类 POI
2. 重新规划切换偏好（火锅→小吃）
3. 雨天路线室内评分更高
4. 少走路路线更紧凑
5. 评论数据已融合到 POI
6. 多样化路线不重复
7. 低预算重新规划降低预算或给出警告

## 技术架构

```
用户输入（自然语言）
    ↓
intent_parser.py    → 意图解析（城市、时间、预算、偏好、场景）
    ↓
poi_retriever.py    → POI 召回（城市筛选 + 偏好匹配 + 评分排序）
    ↓
ugc_analyzer.py     → UGC 评论融合（8维特征提取，30%权重混合）
    ↓
route_optimizer.py  → 路线生成（Beam Search，top-3 多样化路线）
    ↓
scorer.py           → 路线评分（质量、预算、紧凑度、排队、多样性）
    ↓
explanation.py      → 中文解释生成
```

路线优化使用 Beam Search 算法，每条路线生成 3-5 个站点，保证至少包含一个餐饮点。三条推荐路线分别面向不同目标：综合最优、少排队优先、低预算优先，通过 Jaccard 相似度控制路线多样性。
