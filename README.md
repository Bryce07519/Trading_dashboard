# my-strategy-dashboard

一个轻量的本地/静态可视化仪表盘，用于展示基于 Binance 期货账户的日度 PnL、资金曲线与关键指标。数据由 `main.py` 通过 ccxt 抓取、清洗并输出到 `data/` 目录，前端 `index.html` 直接读取该目录下的 JSON/PNG 文件进行渲染。

## 功能
- 从 Binance（支持 USDT-M/COIN-M/现货可按需扩展）拉取历史成交
- 聚合生成日度 PnL（`data/daily_pnl.csv`）
- 计算关键统计指标并输出为 `data/stats.json`
- 生成资金曲线图 `data/equity_curve.png` 与 PnL 分布图 `data/pnl_hist.png`
- 静态页面 `index.html` 自动加载并展示指标与图表
- 提供 `update.sh` 一键更新并推送变更到 Git（可用于 GitHub Pages 展示）

## 目录结构
```
my-strategy-dashboard/
├─ index.html              # 前端页面(静态读取 data/*)
├─ main.py                 # 数据抓取与统计可视化脚本
├─ update.sh               # 一键更新并推送
├─ requirements.txt        # Python 依赖
├─ data/                   # 输出目录（脚本自动创建/更新）
│  ├─ daily_pnl.csv
│  ├─ stats.json
│  ├─ equity_curve.png
│  └─ pnl_hist.png
└─ .gitignore
```

## 环境依赖
- Python 3.9+（建议）
- 包依赖见 `requirements.txt`：`ccxt`, `pandas`, `matplotlib`, `seaborn`, `python-dotenv`

安装依赖：
```bash
pip install -r requirements.txt
```

## 准备 .env（必需）
在项目根目录创建 `.env`，示例：
```ini
# 交易所与凭证
BINANCE_API_KEY=你的APIKey
BINANCE_API_SECRET=你的APISecret
# 交易所类型：binanceusdm | binancecoinm | binance
BINANCE_EXCHANGE_ID=binanceusdm

# 可选：指定合约名单（二选一）
# Base64 编码的逗号分隔字符串（优先使用）
# 例："BTC/USDT:USDT,ETH/USDT:USDT" -> Base64 后填入
BINANCE_SYMBOLS_B64=
# 明文逗号分隔
BINANCE_SYMBOLS_CSV=
```
说明：
- 若未提供 `BINANCE_SYMBOLS_B64`/`BINANCE_SYMBOLS_CSV`，脚本会自动枚举交易所中“线性合约”，并且不会在日志中打印真实合约名（仅打印数量）。
- API 权限至少需要读取成交历史。

## 可配置项（在 `main.py` 顶部）
- `START_DATE_STR`: 从该 UTC 日期开始抓取（默认 `2025-10-16`）
- `INITIAL_CAPITAL`: 初始资金，用于计算资金曲线
- `WINDOW_MS`, `REQUEST_LIMIT`, `SLEEP_SEC`: 抓取分页与限频设置

## 使用方法
1) 运行数据管道生成/更新 `data/`：
```bash
python3 main.py
```
完成后会在 `data/` 目录生成/更新：
- `daily_pnl.csv`
- `stats.json`
- `equity_curve.png`
- `pnl_hist.png`

2) 查看仪表盘：
- 直接用浏览器打开 `index.html`
- 或开启一个本地静态服务器，例如：
```bash
python3 -m http.server 8000
# 然后访问 http://localhost:8000/
```

3) 一键更新并推送（可选）：
```bash
bash update.sh
```
该脚本会：
- 执行 `python3 main.py`
- `git add` 变更的数据与图表
- 若有变更则自动 `commit` 并 `push` 到 `main` 分支

> 如用于 GitHub Pages，将仓库设置为 Pages 来源（例如 `main` 分支 / 根目录），即可在线查看 `index.html`。

## 前端展示说明（`index.html`）
- 页面在加载时从 `data/stats.json` 读取并渲染统计卡片
- 同时展示 `data/equity_curve.png` 与 `data/pnl_hist.png`
- 采用时间戳参数避免浏览器缓存（`?t=...`）

## 常见问题
- 无数据或图表未生成：
  - 检查 `.env` 是否配置正确、API 权限是否具备
  - 确认 `START_DATE_STR` 是否早于你的真实成交日期
- 报错“不支持的 BINANCE_EXCHANGE_ID”：
  - 将 `BINANCE_EXCHANGE_ID` 设置为 `binanceusdm`、`binancecoinm` 或 `binance`
- 指定的合约无效：
  - `.env` 中的合约名需与 `exchange.markets` 匹配；脚本会自动过滤无效合约并给出提示
- 页面不显示数据：
  - 确认 `data/stats.json`、`data/equity_curve.png`、`data/pnl_hist.png` 已生成且与 `index.html` 同一根目录层级下的 `data/`

## 免责声明
本项目仅用于个人回测与数据可视化演示，不构成任何投资建议。使用 API 与账户信息需自行承担风险，请妥善保管密钥与数据。

