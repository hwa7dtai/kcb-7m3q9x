# 云端方案（GitHub）：不用开电脑，手机随时看课表

思路：**数据存手机本地，GitHub 只负责“定时去教务系统抓一次 + 托管网页外壳与最新快照”**。

```
GitHub Actions（每天 05:30 自动跑）
   └─ 用 Secrets 里的学号密码登录教务系统 → 抓课表 → 生成 schedule.json
GitHub Pages
   └─ 托管网页外壳（demo/）+ schedule.json
手机浏览器 / 添加到主屏幕
   └─ 打开即读本地缓存；点「同步最新」才联网拉 schedule.json
```

## 已就绪的仓库

- 代码仓库：https://github.com/hwa7dtai/kcb-7m3q9x
- 站点地址：https://hwa7dtai.github.io/kcb-7m3q9x/（首次发布后生效）
- 接下来只剩两步：填 Secrets → 点一次 Run workflow（见下文第 3、5 节）

## 一次性配置（约 5 分钟）

### 1. 建仓库（已完成）

- 打开 https://github.com/new
- Repository name：例如 `kcb-8f3a2c`（**随便起，别用真实姓名/学号**；越难猜越好）
- 可见性：**Public**（免费版 GitHub Pages 只支持公开仓库）
- 不要勾选 README / .gitignore / license

> 代价说明：Pages 页面是公网可访问的。已经做了两道处理：发布的 JSON **不含学号和姓名**；
> 仓库名建议随机，降低被翻到的概率。

### 2. 上传代码

把本项目全部文件推到这个仓库（可以让我帮你推，或按 GitHub 网页提示上传 zip 解压后的内容）。
必须包含：`demo/`、`server/`、`.github/workflows/publish.yml`。

### 3. 配置账号密码（Secrets）

仓库页 → **Settings → Secrets and variables → Actions → New repository secret**：

| Name | Value |
|---|---|
| `JWXT_SID` | 你的学号 |
| `JWXT_PWD` | 教务系统密码 |

Secrets 加密保存，日志里不会出现。

### 4. 打开 Pages

仓库页 → **Settings → Pages → Build and deployment → Source** 选 **GitHub Actions**。

### 5. 跑第一次同步

仓库页 → **Actions** → 左侧「同步课表并发布」→ 右侧 **Run workflow** → 绿色按钮。
约 2~3 分钟后：

- 成功：页面地址为 `https://<你的用户名>.github.io/<仓库名>/`
- 失败：点进那次运行看红色步骤日志（最常见是教务系统拦截了 GitHub 的国外 IP）

### 6. 手机使用

1. 手机浏览器打开上面的地址（**必须 https**，Pages 自带）
2. 菜单里「添加到主屏幕」→ 以后像 App 一样全屏打开
3. 首次打开显示空/演示数据 → 去「课程管理」点「**同步最新**」拉取课表
4. 之后即使断网，打开也是上次同步的数据；课表有变再点一次「同步最新」

## 日常维护

- 每天 05:30（北京时间）自动同步一次，失败会给你发 GitHub 通知
- 想立即更新：Actions → Run workflow（手机上也能操作），然后回 App 点「同步最新」
- 学期/开学日期变了：改 `server/config.py` 里的 `SEMESTER_START_DATE`

## 已知限制

- **教务系统可能拦国外 IP**：GitHub 的服务器在美国，若首次运行就 403/超时，这个方案就不可行，
  需要换国内云服务器（方案 B）。届时告诉我运行日志，我帮你判断。
- Pages 站点公网可见（已脱敏，但课程名/教室仍可能被看到；介意就换方案 B）
- 自动同步是“每天一次”，不是实时；需要最新就手动 Run workflow + 同步
