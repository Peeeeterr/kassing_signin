# 学搭子自动化打卡助手 (kassing-signin) v1.0

> 作者：@护盾电池  
> 项目仓库：https://github.com/Peeeeterr/kassing_signin

基于逆向分析学搭子平台前端渲染与网络通信协议构建的自动化签到工具。实现时段自动检测、定位离散采样、自适应水印合成、滑动窗口照片冷却与打卡闭环。

---

## 核心机制

- 动态照片冷却：单参数控制冷却期（最低 9 次，覆盖 3 天轮转），强制底图数量达到「冷却池 + 8 张」，规避图像重复审查。
- 极坐标离散定位：在允许半径内均匀生成经纬度并附带随机精度 Jitter，模拟真实移动端定位。
- 水印与 EXIF 自适应：对齐官方 Canvas 阵列水印排版，自动纠正手机横竖屏朝向，并动态控制图片体积在 1MB 以内。
- 跨平台防风控调度：内置 Linux (crontab) 与 Windows (Task Scheduler) 启动脚本，加入随机延时（Jitter）杜绝固定秒级特征。
- 东八区强制锁定：内部时间解析与接口格式化强制锁定 UTC+8（中国标准时间），消除服务器时区配置差异。

---

## 项目结构

```text
kassing-signin/
├── main.py                 主运行程序（支持 -init 向导、倒计时与命令行参数）
├── kassing_signin/         核心功能模块包
│   ├── __init__.py
│   ├── config.py           配置解析、极坐标离散算法与冷却池调度
│   ├── kassing_api.py      官方接口通信（登录鉴权、时段查询、对象存储上传、提交打卡）
│   └── watermark.py        EXIF 朝向校正与 Canvas 阵列水印合成引擎
├── PhotoStorage/           待打卡底图仓库（需存放 冷却池 + 8 张日常照片）
├── Archives/               打卡生成水印照片归档目录
├── run_cron.sh             Linux 定时执行脚本（含随机延时与日志写入）
├── run_windows.bat         Windows 批处理执行脚本
├── run_silent.vbs          Windows 后台静默运行脚本（无控制台窗口）
├── requirements.txt        Python 依赖清单
├── .env.example            配置文件模版
└── .gitignore              Git 版本忽略规则
```

---

## 配置与使用指引

### 天才第零步：点个Star
项目仓库：https://github.com/Peeeeterr/kassing_signin

如果你遇到了配置文件错误的问题，请到该仓库下载最新版。如果问题没有解决，请到该仓库提交Issues。

如果有帮你节省时间，希望你能来点一个Star。

### 步骤一：安装依赖
环境要求 Python 3.9 或更高版本。在项目根目录下执行：
```bash
pip install -r requirements.txt
```

### 步骤二：运行初始化向导
首次运行请在终端执行初始化命令：
```bash
python main.py -init
```
向导将依次引导完成以下配置：
1. 账号与密码：输入学搭子登录学号/工号及密码；
2. 冷却池配置：设定照片冷却期次数（系统最低要求 9 次，直接回车默认 9）；
3. 底图准备与校验：将日常照片拷贝至 `PhotoStorage/` 目录（数量需达到「冷却池 + 8 张」，默认至少 17 张；注意尽量避免包含窗外日光，以防夜间打卡违和），按回车自动校验照片数量；
4. 运行参数确认：确认定位半径（建议 10 ~ 150 米，直接回车默认 50 米）；
5. 自动生成 `.env`：保存并完成本地环境初始化。

### 步骤三：手动验证打卡
初始化完成后，可手动运行以验证登录状态与流程闭环：
```bash
python main.py
```
程序默认带有 10 秒缓冲倒计时（按 Ctrl+C 可中止）。如需跳过倒计时直接打卡，可添加 `-y` 参数：
```bash
python main.py -y
```

### 步骤四：自动化定时部署

#### 1. Linux 服务器部署 (crontab)
赋予执行脚本权限：
```bash
chmod +x run_cron.sh
```
执行 `crontab -e`，在配置末尾添加以下内容（请将 `/path/to/kassing-signin` 替换为实际项目绝对路径）：
```cron
CRON_TZ=Asia/Shanghai

# 早读打卡 (周一至周五 08:00 启动，300 秒内随机延时，打卡在 08:00 至 08:05)
00 08 * * 1-5 /path/to/kassing-signin/run_cron.sh 300

# 晚自习开始打卡 (周一至周五 18:16 启动，180 秒内随机延时，打卡在 18:16 至 18:19)
16 18 * * 1-5 /path/to/kassing-signin/run_cron.sh 180

# 晚自习结束打卡 (周一至周五 20:40 启动，300 秒内随机延时，打卡在 20:40 至 20:45)
40 20 * * 1-5 /path/to/kassing-signin/run_cron.sh 300
```

#### 2. Windows 电脑部署 (任务计划程序)
以管理员身份打开命令提示符 (CMD) 或 PowerShell，依次执行以下命令注册周一至周五计划任务（请将 `D:\kassing-signin` 替换为实际项目绝对路径）：
```cmd
schtasks /create /tn "Kassing_Morning" /tr "wscript.exe \"D:\kassing-signin\run_silent.vbs\" 300" /sc weekly /d MON,TUE,WED,THU,FRI /st 08:00 /f
schtasks /create /tn "Kassing_EveningStart" /tr "wscript.exe \"D:\kassing-signin\run_silent.vbs\" 180" /sc weekly /d MON,TUE,WED,THU,FRI /st 18:16 /f
schtasks /create /tn "Kassing_EveningEnd" /tr "wscript.exe \"D:\kassing-signin\run_silent.vbs\" 300" /sc weekly /d MON,TUE,WED,THU,FRI /st 20:40 /f
```
说明：Windows 方案通过 `run_silent.vbs` 调度 `run_windows.bat`，在后台完全静默运行，不会弹出控制台窗口。

#### 3. 调休或节假日手动暂停打卡
如果遇到调休、放假或特殊情况需要临时取消打卡，可通过以下任意方式处理：

方式一（快速文件标记，推荐）：
在项目根目录创建名为 `.pause` 的空文件即可临时阻断打卡，无需改动系统定时任务；调休结束删除该文件即可自动恢复：
- Linux 暂停：`touch .pause`，恢复：`rm .pause`
- Windows 暂停：`type nul > .pause`，恢复：`del .pause`

方式二（系统定时任务管理）：
- Linux: 执行 `crontab -e`，在对应打卡规则前添加 `#` 注释保存；恢复时移除 `#`。彻底取消直接删除对应行；
- Windows: 管理员 CMD 执行以下命令快速禁用任务（恢复时将 `/disable` 换为 `/enable`）：
  ```cmd
  schtasks /change /tn "Kassing_Morning" /disable
  schtasks /change /tn "Kassing_EveningStart" /disable
  schtasks /change /tn "Kassing_EveningEnd" /disable
  ```
  彻底取消并删除任务：
  ```cmd
  schtasks /delete /tn "Kassing_Morning" /f
  schtasks /delete /tn "Kassing_EveningStart" /f
  schtasks /delete /tn "Kassing_EveningEnd" /f
  ```

---

## 运行日志查看
所有通过定时脚本执行的打卡记录、定位坐标、随机延时及服务器响应均自动记录于 `logs/cron.log`。
查看最新执行日志：
- Linux 终端：`tail -n 50 logs/cron.log`
- Windows：使用文本编辑器打开 `logs\cron.log`


