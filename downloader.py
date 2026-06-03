import requests
import re
import json
import os
import argparse
import time
import random
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

def get_video_info(url):
    """提取视频信息并获取直链"""
    sess = requests.Session()
    # 模拟浏览器环境
    sess.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    })
    
    print(f"正在分析视频页面: {url}")
    try:
        res = sess.get(url)
        res.raise_for_status()
    except Exception as e:
        print(f"页面请求失败: {e}")
        return None

    # 尝试提取 ld+json 中的博主名
    soup = BeautifulSoup(res.text, 'html.parser')
    json_lds = soup.find_all('script', type='application/ld+json')
    author_name = "Unknown_Author"
    for tag in json_lds:
        try:
            ld_data = json.loads(tag.text)
            if isinstance(ld_data, dict) and 'author' in ld_data and isinstance(ld_data['author'], str):
                author_name = ld_data['author']
        except Exception:
            pass
            
    # 清理非法的目录名称字符
    author_name = re.sub(r'[\\/*?:"<>|]', "", author_name).strip()
    if not author_name:
        author_name = "Unknown_Author"

    # 提取 flashvars 包含所有必要的媒体信息
    match = re.search(r'var\s+flashvars_\d+\s*=\s*(\{.*?\});', res.text)
    if not match:
        print("未找到视频数据, 页面结构可能已更改或该视频不可用。")
        return None

    try:
        data = json.loads(match.group(1))
        
        # 清理标题名称作为文件名
        title = data.get('video_title', 'downloaded_video')
        title = re.sub(r'[\\/*?:"<>|]', "", title)
        print(f"视频标题: {title}")

        # 从 mediaDefinitions 找到 mp4 格式的视频接口 (get_media)
        mp4_get_media_urls = [
            v['videoUrl'] for v in data.get('mediaDefinitions', []) 
            if v.get('format') == 'mp4' and isinstance(v.get('videoUrl'), str)
        ]
        
        if not mp4_get_media_urls:
            print("未找到 MP4 格式的解析接口。")
            return None
            
        get_media_url = mp4_get_media_urls[0]
        
        # 请求 get_media 接口获取真实的直接下载链接列表
        print("正在获取真实视频直链...")
        media_res = sess.get(get_media_url)
        media_res.raise_for_status()
        
        # get_media 返回一个 JSON 数组，包含所有可用的分辨率
        available_videos = media_res.json()
        
        if not available_videos:
             print("获取直链失败：返回为空。")
             return None
             
        # 按照分辨率高度排序，获取最高画质
        available_videos.sort(key=lambda x: int(x.get('height', 0)), reverse=True)
        
        best_video = available_videos[0]
        print(f"解析成功, 找到最佳画质: {best_video.get('quality', '未知')}P")
        
        return {
            'title': title,
            'url': best_video.get('videoUrl'),
            'quality': best_video.get('quality'),
            'author': author_name,
            'poster_url': data.get('image_url'),
            'original_url': url,
            'session': sess # 保留会话用于下载
        }
        
    except json.JSONDecodeError:
        print("解析 JSON 数据失败。")
        return None
    except Exception as e:
        print(f"解析过程中出错: {e}")
        return None

def download_video(info, output_dir, position=0):
    """下载视频文件"""
    if not info or not info.get('url'):
        return False
        
    author = info.get('author', 'Unknown_Author')
    title = info['title']
    video_dir = os.path.join(output_dir, author, title)
    
    if not os.path.exists(video_dir):
        os.makedirs(video_dir)
        
    output_file = os.path.join(video_dir, f"{title}.mp4")
    
    sess = info['session']
    
    # 写入 Emby nfo
    nfo_path = os.path.join(video_dir, f"{title}.nfo")
    if not os.path.exists(nfo_path):
        nfo_content = f'''<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<movie>
  <title>{title}</title>
  <studio>{author}</studio>
  <actor>
    <name>{author}</name>
  </actor>
  <website>{info.get('original_url', '')}</website>
</movie>'''
        with open(nfo_path, 'w', encoding='utf-8') as f:
            f.write(nfo_content)
            
    # 下载 poster (如果存在且未下载)
    poster_path = os.path.join(video_dir, 'poster.jpg')
    if info.get('poster_url') and not os.path.exists(poster_path):
        try:
            # P站的 CDN 可能需要对应的 sess 以及 Referer
            pres = sess.get(info['poster_url'], headers={'Referer': 'https://cn.pornhub.com/'}, timeout=15)
            if pres.status_code == 200:
                with open(poster_path, 'wb') as f:
                    f.write(pres.content)
            else:
                 pass
        except Exception as e:
            pass
    try:
        # P站的流媒体服务器需要 Referer 和正确的 Cookies
        headers = {
             'Referer': 'https://cn.pornhub.com/'
        }
        
        # 获取文件总大小
        total_size = 0
        with sess.get(info['url'], headers=headers, stream=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))

        downloaded = 0
        block_size = 8192
        max_retries = 10
        retry_count = 0
        
        # 初始化 tqdm 进度条
        pbar = None
        if total_size > 0:
            short_title = info['title'][:20] + '..' if len(info['title']) > 20 else info['title']
            pbar = tqdm(total=total_size, initial=0, unit='B', unit_scale=True, desc=short_title, position=position, leave=True)

        while downloaded < total_size or total_size == 0:
            if retry_count > 0:
                 # 使用 Range header 进行断点续传
                 headers['Range'] = f'bytes={downloaded}-'
                 
            try:
                # 以 append 模式打开文件如果是在重试
                mode = 'ab' if downloaded > 0 else 'wb'
                with sess.get(info['url'], headers=headers, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    # 如果服务器不支持断点续传，或者返回了新的流
                    if r.status_code == 200 and downloaded > 0:
                        downloaded = 0
                        mode = 'wb'
                        if pbar: pbar.n = 0; pbar.refresh()
                        
                    with open(output_file, mode) as f:
                        for chunk in r.iter_content(chunk_size=block_size):
                            if chunk:
                                f.write(chunk)
                                chunk_len = len(chunk)
                                downloaded += chunk_len
                                if pbar:
                                    pbar.update(chunk_len)
                
                # 如果没有异常退出循环说明下载完成了
                if total_size == 0 or downloaded >= total_size:
                     break
                     
            except Exception as e:
                # 对于 IncompleteRead 之类的异常也会被捕获
                retry_count += 1
                if retry_count > max_retries:
                    if pbar: pbar.write(f"下载失败，已达到最大重试次数: {info['title']}")
                    return False
                continue

        if pbar:
            pbar.close()
        return True
            
    except Exception as e:
        print(f"\n获取文件信息失败: {e}")
        return False

def get_author_videos(author_url):
    """解析博主页面的所有视频链接"""
    sess = requests.Session()
    sess.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    })
    
    print(f"正在获取博主主页: {author_url}")
    video_links = set()
    page = 1
    
    # 自动处理不同类型的博主URL结构以进入视频列表
    # 例如 /model/name/videos
    if '/videos' not in author_url:
        author_url = author_url.rstrip('/') + '/videos'
        print(f"自动转到视频列表页: {author_url}")
        
    while True:
        url = f"{author_url}?page={page}"
        print(f"正在抓取第 {page} 页...")
        
        # 增加随机延时防止封禁
        if page > 1:
            time.sleep(random.uniform(1.0, 3.0))
            
        try:
            res = sess.get(url, timeout=15)
            res.raise_for_status()
            
            soup = BeautifulSoup(res.text, 'html.parser')
            # P站视频列表中的视频通常在 id 为 videoCategory 的 ul 下，或者直接找所有的 video_url
            # 这里找所有包含 viewkey 的链接
            links_found = False
            for a in soup.find_all('a', href=True):
                href = a['href']
                if 'view_video.php?viewkey=' in href:
                    full_url = "https://cn.pornhub.com" + href if href.startswith('/') else href
                    if full_url not in video_links:
                        video_links.add(full_url)
                        links_found = True
            
            # 如果这一页没有找到任何视频链接，或者是到了尽头
            if not links_found:
                 print("没有找到更多视频，抓取结束。")
                 break
                 
            # 检查是否有下一页按钮
            next_button = soup.find('li', class_='page_next')
            if not next_button or not next_button.find('a'):
                 print("到达最后一页，抓取结束。")
                 break
                 
            page += 1
            
        except requests.exceptions.RequestException as e:
            print(f"获取博主页面第 {page} 页失败: {e}，将重试...")
            time.sleep(3)
            continue
        except Exception as e:
            print(f"解析博主页面发生未知错误: {e}")
            break
            
    return list(video_links)

def main():
    parser = argparse.ArgumentParser(description='Pornhub 视频下载器 (Python 原生实现)')
    parser.add_argument('url', help='要下载的视频URL或博主URL')
    parser.add_argument('-o', '--output', default='.', help='保存目录')
    parser.add_argument('-t', '--threads', type=int, default=3, help='并发下载线程数(仅博主模式有效)')
    
    args = parser.parse_args()
    
    url = args.url
    
    if 'viewkey=' in url:
        # 单个视频下载
        info = get_video_info(url)
        if info:
            download_video(info, args.output)
    elif '/model/' in url or '/pornstar/' in url or '/channel/' in url:
        # 博主/频道下载
        print(f"检测到博主/频道链接: {url}")
        video_urls = get_author_videos(url)
        if video_urls:
            print(f"找到 {len(video_urls)} 个视频，开始并发下载(线程数: {args.threads})...")
            
            # 使用 ThreadPoolExecutor 并发处理
            def process_and_download(v_url, position):
                info = get_video_info(v_url)
                if info:
                    download_video(info, args.output, position=position)
                    
            with ThreadPoolExecutor(max_workers=args.threads) as executor:
                futures = []
                for i, v_url in enumerate(video_urls):
                    # 分配进度条显示行，避免过多重叠
                    position = i % args.threads
                    futures.append(executor.submit(process_and_download, v_url, position))
                
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception:
                        pass
            print("\n博主所有视频批量下载处理完成！")
        else:
             print("未能解析到该博主的视频列表。")
    else:
        print("不支持的URL格式。请提供单个视频链接 (含 viewkey=) 或博主链接 (含 /model/, /pornstar/, /channel/)。")

if __name__ == "__main__":
    main()
