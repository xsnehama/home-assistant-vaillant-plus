# home-assistant-vaillant-plus
> [!IMPORTANT]
> ## 中文增强维护版说明
>
> 本仓库是 [daxingplay/home-assistant-vaillant-plus](https://github.com/daxingplay/home-assistant-vaillant-plus) 的公开 Fork，遵循原项目的 Apache-2.0 许可证并保留原作者版权信息。本分支不是从零重写，而是在上游基础上，针对实际 Home Assistant 环境中影响日常使用的问题进行修复和增强。
>
> 相比上游，本分支目前包含以下关键改进：
>
> - **增强登录稳定性**：增加主动刷新令牌、认证失效后重新登录，以及 WebSocket 自动重连，降低长期运行后设备失联的概率。
> - **修复实体可用性判断**：连接断开时实体会正确显示为不可用，避免把缓存的历史数据误认为实时状态。
> - **修复二进制传感器状态**：按设备协议中的明确状态值判断开关状态，避免简单布尔转换造成误报。
> - **改善数值统计兼容性**：运行时间、功率、转速等保持为真正的数值，并补充单位和状态类别，便于 Home Assistant 统计、图表及自动化比较。
> - **完善诊断信息**：兼容更多诊断字段，补充常见故障码中文说明，并将“未接传感器”等情况作为状态属性表达。
> - **修复生活热水温度显示**：过滤无效的水箱温度，在缺少有效读数时按目标温度和出水温度合理回退。
> - **优化日志级别**：将高频调试信息降为 `debug`，保留真正需要关注的异常，减少日志膨胀和磁盘写入。
>
> 上述修改已在本 Fork 维护者自己的 Home Assistant 与威能设备环境中实际运行验证。不同设备型号、固件和区域服务可能存在差异，更新前请保留备份。

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![Coverage][coverage-shield]][coverage]
![GitHub all releases][download-all]
![GitHub release (latest by SemVer)][download-latest]
[![License][license-shield]][license]

[![hacs][hacsbadge]][hacs]
[![Project Maintenance][maintenance-shield]][user_profile]
[![BuyMeCoffee][buymecoffeebadge]][buymecoffee]

[![Community Forum][forum-shield]][forum]

Home Assistant custom component for controlling vSmart in Vaillant+ cn app.

## Screenshot

![screenshot](docs/images/screenshot-all.jpg)

## Installation

### Pre-requirements
- You need connect your Vaillant vSmart device through Vaillant+([iOS](https://apps.apple.com/cn/app/%E5%A8%81%E7%AE%A1%E5%AE%B6/id1465568192) | Android ) App.

### Installation Methods
#### HACS
Click the following link to add to your Home Assistant.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=daxingplay&repository=home-assistant-vaillant-plus&category=integration)

Or you can search for `Vaillant Plus` in your HACS.

#### Manual
Copy `custom_components/vaillant_plus` into your Home Assistant `config` directory.

### Post installation steps
- Restart HA
- Search for this integration in `Settings -> Devices & Services`
- Click `Add integration` and search for `Vaillant Plus`
- Click `Configure` in Vaillant Plus integration to start config flow
- Enter your username and password for the Vaillant+ App
- If login successfully, select the proper Vaillant vSmart device from the list
- All done

## Contributions are welcome!
If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

Component built with integration_blueprint.

***

[vaillant-plus]: https://github.com/daxingplay/home-assistant-vaillant-plus
[buymecoffee]: https://www.buymeacoffee.com/daxingplay
[buymecoffeebadge]: https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=flat-square
[commits-shield]: https://img.shields.io/github/commit-activity/y/daxingplay/home-assistant-vaillant-plus.svg?style=flat-square
[commits]: https://github.com/daxingplay/home-assistant-vaillant-plus/commits/master
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=flat-square
[coverage-shield]: https://img.shields.io/coverallsCoverage/github/daxingplay/home-assistant-vaillant-plus?style=flat-square
[coverage]: https://coveralls.io/github/daxingplay/home-assistant-vaillant-plus?branch=master
[exampleimg]: example.png
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=flat-square
[forum]: https://github.com/daxingplay/home-assistant-vaillant-plus/issues
[license]: https://github.com/daxingplay/home-assistant-vaillant-plus/blob/master/LICENSE
[license-shield]: https://img.shields.io/github/license/daxingplay/home-assistant-vaillant-plus.svg?style=flat-square
[maintenance-shield]: https://img.shields.io/badge/maintainer-daxingplay-blue.svg?style=flat-square
[releases-shield]: https://img.shields.io/github/release/daxingplay/home-assistant-vaillant-plus.svg?style=flat-square
[releases]: https://github.com/daxingplay/home-assistant-vaillant-plus/releases
[user_profile]: https://github.com/daxingplay
[download-all]: https://img.shields.io/github/downloads/daxingplay/home-assistant-vaillant-plus/total?style=flat-square
[download-latest]: https://img.shields.io/github/downloads/daxingplay/home-assistant-vaillant-plus/latest/total?style=flat-square

