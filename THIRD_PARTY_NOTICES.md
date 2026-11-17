# 第三方软件与数据说明

本项目包含或使用下列第三方软件、公共数据及在线服务。项目自己的授权方式与下列第三方各自的许可是不同的；本文件不会替代各自的许可证。

## 随项目分发的软件

- **Leaflet 1.9.4** — BSD 2-Clause。版权所有者和许可全文：`static/vendor/leaflet/LICENSE`。项目使用了其浏览器发行文件。[上游项目](https://github.com/Leaflet/Leaflet)
- **Apache ECharts 5.6.0** — Apache License 2.0。许可全文：`static/vendor/echarts/LICENSE`；原始声明：`static/vendor/echarts/NOTICE`。ECharts 的部分组件包含 d3.js 的 BSD 3-Clause 许可代码，相关许可及版权声明：`static/vendor/echarts/licenses/LICENSE-d3`。[上游项目](https://github.com/apache/echarts/tree/5.6.0)
- Python 依赖通过 `requirements.txt` 安装，不随本仓库携带虚拟环境；各依赖及其传递依赖受其各自的许可约束。

## 公开数据与服务

- **OpenStreetMap** — 地图及 OSRM 路线所基于的路网数据：© [OpenStreetMap contributors](https://www.openstreetmap.org/copyright)，[Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/1-0/)。本仓库的离线路线样本由公开 OSRM 服务查询结果保存；项目会采样和显示路线。ODbL 对数据库及可能的衍生数据库有具体条款，应按实际使用情况遵守，不将项目代码自动视为 ODbL 数据库。公开瓦片服务另有[使用政策](https://operations.osmfoundation.org/policies/tiles/)。
- **Open-Meteo** — [天气数据与历史预报](https://open-meteo.com/)以 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) 提供。项目对数据进行了采样选择、时间对齐和风险分级；风险等级为项目推断，并非数据提供者发布的预警。接口服务还受 [Open-Meteo 服务条款](https://open-meteo.com/en/terms)约束；免费 API 仅供非商业用途。
- **GeoNames** — [地理名称数据](https://www.geonames.org/)通过 Open-Meteo 地点服务提供，遵循 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。项目根据输入筛选地点。
- **Natural Earth** — 离线矢量地图摘取了湖北、湖南、广东的边界，来自 [Natural Earth](https://www.naturalearthdata.com/)，其地图数据属于[公共领域](https://www.naturalearthdata.com/about/terms-of-use/)。
- **OSRM** — 路线由 [OSRM 演示服务](https://project-osrm.org/)计算，项目不包含 OSRM 服务端源码；服务的可用性和使用限制应另行核对。
