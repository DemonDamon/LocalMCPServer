import requests
from bs4 import BeautifulSoup
import markdownify
import os
import urllib.parse
import re
from urllib.parse import urljoin
import hashlib
import time
import argparse

"""
usage:
1. python crawler_to_md.py --url https://example.com --save_dir ./output
2. python crawler_to_md.py --save_dir ./output
"""

# 不需要下载的图片格式
IGNORED_EXTENSIONS = ['.ico', '.webp', '.svg', '.gif', '.bmp', '.tiff']

def sanitize_filename(filename):
    """
    清理文件名，移除不允许的字符
    """
    # 确保文件名不为None
    if filename is None:
        return "untitled"
    
    # 替换换行符和制表符
    filename = filename.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    
    # 替换Windows和Unix系统不允许的字符
    invalid_chars = r'[\\/*?:"<>|]'
    sanitized = re.sub(invalid_chars, '_', filename)
    
    # 替换多个连续空格为单个空格
    sanitized = re.sub(r'\s+', ' ', sanitized)
    
    # 限制长度，避免文件名过长
    if len(sanitized) > 100:
        sanitized = sanitized[:97] + '...'
    
    # 移除前后空白
    sanitized = sanitized.strip()
    
    # 确保文件名不为空
    if not sanitized:
        sanitized = "untitled"
    
    return sanitized

def should_download_image(img_url):
    """
    判断图片是否需要下载
    """
    # 检查URL扩展名
    parsed_url = urllib.parse.urlparse(img_url)
    path = parsed_url.path.lower()
    
    # 检查是否是忽略的扩展名
    for ext in IGNORED_EXTENSIONS:
        if path.endswith(ext):
            print(f"跳过下载: {img_url} (忽略的格式: {ext})")
            return False
    
    return True

def download_image(img_url, base_url, img_folder):
    """
    下载图片并返回本地路径
    """
    try:
        # 处理相对URL
        if not img_url.startswith(('http://', 'https://')):
            img_url = urljoin(base_url, img_url)
        
        # 检查是否应该下载此图片
        if not should_download_image(img_url):
            return None
        
        # 创建图片文件名 (使用URL的哈希值作为文件名，避免文件名冲突)
        img_hash = hashlib.md5(img_url.encode()).hexdigest()
        
        # 获取原始扩展名或默认为.jpg
        # 提取文件扩展名
        extension = os.path.splitext(urllib.parse.urlparse(img_url).path)[1]
        if not extension or len(extension) > 5:  # 检查扩展名是否合法
            extension = '.jpg'
        
        img_filename = f"{img_hash}{extension}"
        img_path = os.path.join(img_folder, img_filename)
        
        # 确保图片目录存在
        os.makedirs(os.path.dirname(img_path), exist_ok=True)
        
        # 检查文件是否已存在
        if not os.path.exists(img_path):
            # 下载图片
            response = requests.get(img_url, stream=True, timeout=10)
            if response.status_code == 200:
                with open(img_path, 'wb') as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
                print(f"下载图片: {img_url} -> {img_path}")
            else:
                print(f"无法下载图片 {img_url}, 状态码: {response.status_code}")
                return None
        
        return img_path
    except Exception as e:
        print(f"下载图片时出错 {img_url}: {str(e)}")
        return None

def process_images(soup, base_url, img_folder, md_file_path):
    """
    处理HTML中的所有图片，下载并替换为本地路径
    """
    for img in soup.find_all('img'):
        src = img.get('src')
        if src:
            # 跳过数据URI
            if src.startswith('data:'):
                continue
            
            # 下载图片
            local_path = download_image(src, base_url, img_folder)
            if local_path:
                # 计算相对于markdown文件的路径
                md_dir = os.path.dirname(md_file_path)
                rel_path = os.path.relpath(local_path, md_dir).replace('\\', '/')
                img['src'] = rel_path
    
    return soup

def replace_md_image_urls(markdown_text, base_url, img_folder, md_file_path):
    """
    替换Markdown中的图片URL为本地路径
    """
    # 匹配Markdown中的图片链接: ![alt](url)
    img_pattern = r'!\[(.*?)\]\((https?://[^)]+)\)'
    
    def replace_url(match):
        alt_text = match.group(1)
        img_url = match.group(2)
        
        # 下载图片
        local_path = download_image(img_url, base_url, img_folder)
        if local_path:
            # 计算相对于markdown文件的路径
            md_dir = os.path.dirname(md_file_path)
            rel_path = os.path.relpath(local_path, md_dir).replace('\\', '/')
            return f'![{alt_text}]({rel_path})'
        return match.group(0)  # 如果下载失败，保持原样
    
    # 替换所有匹配的图片URL
    return re.sub(img_pattern, replace_url, markdown_text)

def fetch_and_convert_to_markdown(url, save_dir='.', img_folder=None):
    """
    获取网页内容，下载图片，并转换为Markdown格式
    
    参数:
    - url: 网页URL
    - save_dir: 保存Markdown和图片的目录
    - img_folder: 图片保存文件夹，如果为None则使用save_dir下的images目录
    """
    try:
        # 确保保存目录存在
        os.makedirs(save_dir, exist_ok=True)
        
        # 如果img_folder为None，则使用save_dir下的images目录
        if img_folder is None:
            img_folder = os.path.join(save_dir, 'images')
        
        # 创建图片文件夹
        os.makedirs(img_folder, exist_ok=True)
        
        # 准备请求头
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
        
        # 发送请求获取网页内容
        response = requests.get(url, headers=headers, timeout=30)
        
        # 检查请求是否成功
        if response.status_code != 200:
            print(f"Error fetching {url}: {response.status_code}")
            return None, None, None
        
        # 解析网页内容
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 提取网页标题
        title = soup.title.string if soup.title else 'Untitled Page'
        # 确保标题不为None
        if title is None:
            title = 'Untitled Page'
        
        # 使用网页标题作为文件名
        sanitized_title = sanitize_filename(title)
        if not sanitized_title:
            sanitized_title = "untitled_page"
            
        # 添加时间戳以避免文件名冲突
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_file = f"{sanitized_title}_{timestamp}.md"
        
        # 完整的md文件路径
        md_file_path = os.path.join(save_dir, output_file)
        
        # 处理图片：下载并替换URL
        soup = process_images(soup, url, img_folder, md_file_path)
        
        # 移除不必要的元素
        for element in soup.select('script, style, iframe, nav, footer, .sidebar, .advertisement, .ads'):
            element.decompose()
        
        # 提取主要内容
        # 尝试识别主要内容区域
        main_content = None
        for selector in ['article', 'main', '.main-content', '.post-content', '.entry-content', '.content', '#content']:
            content = soup.select_one(selector)
            if content:
                main_content = content
                break
        
        # 如果没有找到主要内容区域，则使用body
        if not main_content:
            main_content = soup.find('body')
            if not main_content:  # 如果连body都没有找到
                main_content = soup
        
        # 将内容转换为Markdown格式
        markdown_content = markdownify.markdownify(str(main_content), heading_style="ATX")
        
        # 替换Markdown文本中的图片URL
        markdown_content = replace_md_image_urls(markdown_content, url, img_folder, md_file_path)
        
        # 生成完整的Markdown文档
        markdown_document = f"# {title}\n\n{markdown_content}"
        
        # 返回文档内容、标题和文件路径
        return markdown_document, title, md_file_path
    
    except Exception as e:
        print(f"处理网页时出错: {str(e)}")
        return None, "Error_Page", None

# 使用示例
if __name__ == "__main__":
    try:
        # 命令行参数解析
        parser = argparse.ArgumentParser(description='将网页转换为Markdown格式并下载相关图片')
        parser.add_argument('--url', help='要爬取的网页URL')
        parser.add_argument('--save_dir', default='.', help='保存Markdown文件和图片的目录，默认为当前目录')
        args = parser.parse_args()
        
        # 获取URL，优先使用命令行参数，其次询问用户
        url = args.url
        if not url:
            url = input("请输入网址: ")
        
        print(f"开始爬取 {url} 的内容...")
        print(f"内容将保存到 {os.path.abspath(args.save_dir)}")
        
        start_time = time.time()
        img_folder = os.path.join(args.save_dir, 'images')
        markdown_output, page_title, md_file_path = fetch_and_convert_to_markdown(url, args.save_dir, img_folder)
        end_time = time.time()
        
        if markdown_output and md_file_path:
            # 保存Markdown文件
            try:
                with open(md_file_path, 'w', encoding='utf-8') as f:
                    f.write(markdown_output)
                
                print(f"内容已成功爬取并保存为 {md_file_path}")
                print(f"处理完成，耗时: {end_time - start_time:.2f} 秒")
                print(f"图片已保存在 '{img_folder}' 目录下")
            except OSError as e:
                # 如果文件名仍有问题，使用简单的默认文件名
                print(f"创建文件时出错: {str(e)}")
                fallback_filename = os.path.join(args.save_dir, f"webpage_{time.strftime('%Y%m%d_%H%M%S')}.md")
                with open(fallback_filename, 'w', encoding='utf-8') as f:
                    f.write(markdown_output)
                print(f"已使用备用文件名保存内容: {fallback_filename}")
        else:
            print("爬取失败，请检查网址是否正确")
    
    except KeyboardInterrupt:
        print("\n程序已被用户中断")
    except Exception as e:
        print(f"程序执行出错: {str(e)}")
        import traceback
        traceback.print_exc()
