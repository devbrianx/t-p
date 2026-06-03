#  下载器

一个用原生 Python 实现的  视频下载脚本。
完全不需要第三方下载器(例如 yt-dlp) 就可以支持 P 站的下载机制。

## 特性
- 支持单个视频下载 (使用网页直链或 `viewkey`)
- 支持批量下载某个博主、模特或频道主页下的所有视频
- 自动解析该视频的最高画质直链进行下载
- 自定义下载保存目录
- 纯 Python `requests` + `beautifulsoup4` 实现

## 准备工作

使用前，请确保安装了所需的 Python 库。

1. 建议使用虚拟环境运行：
```powershell
python -m venv venv
.\venv\Scripts\activate
```

2. 安装依赖：
```powershell
pip install -r requirements.txt
```

或者手动安装：
```powershell
pip install requests beautifulsoup4
```

## 使用说明

脚本的基本使用格式：
```powershell
python downloader.py <视频或博主URL> [-o 输出目录]
```

### 1. 下载单个视频
将视频 URL 作为参数传入：
```powershell
python downloader.py "https://cn.pornhub.com/view_video.php?viewkey=69b41a264f204"
```
视频将会被默认保存在当前文件夹内。

### 2. 下载博主/频道页的所有视频
将频道或博主的 URL 作为参数传入即可：
```powershell
python downloader.py "https://cn.pornhub.com/model/brian"
```
注意：抓取博主下全部视频时可能需要花费一些时间来解析所有页面。

### 3. 指定保存路径
使用 `-o` 或 `--output` 选项指定视频保存的目录。如果目录不存在，脚本会自动创建：
```powershell
python downloader.py "https://cn.pornhub.com/view_video.php?viewkey=69b41a264f204" -o "D:\downloads\ph"
```

## 注意事项
1. **网络连接**：由于该站点的特殊性，确保您的网络环境能够正常访问该网站。
2. **反爬限制**：频繁且大量的下载可能会触发网站的安全限制。如果遇到 "页面请求失败" 等错误，请稍后再试。
3. **免责声明**：此脚本仅供技术学习与交流参考，请勿用于违反当地法律法规及网站服务条款的用途。
