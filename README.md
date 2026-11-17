# 运输路线天气风险预警与应对决策

这是本机运行的中文 Web 产品原型。Python 使用 OSRM 真实路由和 Open-Meteo 天气计算沿途风险及调度建议；不需要 Java。

## 安装和启动

需要 Python 3.11 或更新版本。在终端进入本项目目录后执行：

```sh
./run.sh
```

首次启动会创建项目内的 `.venv` 并安装 `requirements.txt`，需要联网；依赖安装完成后，可断网启动并使用已覆盖的离线演示。启动后访问 `http://localhost:8000`，在终端按 Control-C 停止。`.venv`、缓存和实际 `.env` 不纳入仓库。

可按 `.env.example` 创建 `.env`；`ROUTER_MODE=osrm` 是目前支持的路由方式，`CACHE_TTL_MIN` 控制路由和天气缓存分钟数。

## 如何演示

- **实时**：输入起终点和计划时间，系统使用 Open-Meteo Geocoding / GeoNames 查询非内置地点，再查询 OSRM 路线和 Open-Meteo 天气。存在同名地点时，可从输入建议中选择带地区的地点；国家或省级中心有唯一匹配时会优先选中，并在结果中显示解析来源。服务没有收录的地点可输入纬度,经度。外部服务不可用时仅回落到匹配的离线快照；时间不覆盖时会明确报错。
- **离线**：选择“离线”并分析默认路线。系统自动选择历史快照范围内的模拟发车时间和参考时刻；也可在离线模式选择模拟场景。快照不是当前预报，不能用于现实调度。
- **场景**：以实时数据为基础加载模拟封路或减速，事件会明确标为模拟。若实时接口不可用，不保证当前时间有匹配的离线天气。
- **已有路线体检**：可输入城市、纬度经度或 GeoJSON LineString。系统对相邻点逐段路由；任一段未缓存或不可达时明确报错。
- 分析后点击路线可查看地图和天气截面，调整偏好可重新计算，点击“一键自动决策”显示建议与条件。若预计超过承诺时效，路线卡、决策卡和报告会提示超时；推荐不代表承诺时效一定能满足。点击“导出报告”会在项目内 `reports/` 新建单文件 HTML，页面提供打开入口；`examples/` 提供样例报告。

离线天气快照是 Open-Meteo 历史预报，不是当前预报，时间仅覆盖 2025-01-01 至 2025-01-02 UTC；三组可复现案例位于 `fixtures/cases/`。快照只覆盖这些路线的默认采样点，改变路线或采样间距可能超出覆盖。找不到匹配的数据或经过时刻超出覆盖时会明确报错。

## 验证

安装依赖后，在项目目录运行 `./.venv/bin/python -m pytest -q`。图表、地图和报告使用项目内保存的 Leaflet、ECharts 与矢量省界数据，不从 CDN 加载脚本。

## 数据来源

- 路线：OSRM 公共服务及 OpenStreetMap，离线文件保存了请求地址与获取时间。
- 地点查询：Open-Meteo Geocoding / GeoNames；内置城市坐标来自原任务提供的坐标表。
- 天气：Open-Meteo 实时预报；离线使用带获取时间的历史预报快照。
- 地图省界：Natural Earth；联网底图为 OpenStreetMap。
- 模拟参数和风险阈值：分别见 `config/assumptions.yaml` 和 `config/thresholds.yaml`；场景事件均标为模拟。详细计算方法见 `docs/decision-logic.md`。

风险等级是系统根据公开天气数据和项目阈值推断的结果，不是官方天气预警或现实封路公告。成本、概率和风险惩罚使用模拟假设，结果不是实际报价或经过验证的统计预测。

## Windows 11 启动

安装 Python 3.11 或更新版本后，在项目目录打开 PowerShell，首次运行：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

之后启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开浏览器访问 `http://localhost:8000`；停止时在 PowerShell 按 Ctrl+C。Windows 运行尚未实机验证。

## 第三方许可与署名

本项目使用的第三方软件、地图和天气数据的来源、许可证与相关声明，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。地图与路线数据 © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright)，遵循 [ODbL](https://opendatacommons.org/licenses/odbl/1-0/)；天气数据来自 [Open-Meteo](https://open-meteo.com/)，地点数据来自 [GeoNames](https://www.geonames.org/)，遵循 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。系统会对数据做采样、时间对齐和风险计算。
