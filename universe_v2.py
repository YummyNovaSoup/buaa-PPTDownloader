import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
import json
import os
import shutil
import img2pdf
import time

# ================= 配置区 =================
USERNAME = "你的账号"
PASSWORD = "你的密码"
TARGET_COURSE_URL = "https://classroom.msa.buaa.edu.cn/livingroom?course_id=115538&sub_id=5377422&tenant_code=21"
# ==========================================

# 这里的 service 参数必须和浏览器里的一模一样，否则 CAS 会报错
LOGIN_URL = "https://sso.buaa.edu.cn/login?service=https%3A%2F%2Fyjapi.msa.buaa.edu.cn%2Fcasapi%2Findex.php%3Fforward%3Dhttps%253A%252F%252Fclassroom.msa.buaa.edu.cn%252F%26r%3Dauth%252Flogin%26tenant_code%3D21"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

def auto_login():
    print("🚀 [1/4] 正在获取登录参数...")
    try:
        resp = session.get(LOGIN_URL)
        soup = BeautifulSoup(resp.text, 'html.parser')
        execution = soup.find('input', {'name': 'execution'})['value']
        event_id = soup.find('input', {'name': '_eventId'})['value']
    except Exception as e:
        print(f"   ❌ 初始化失败: {e}")
        return False

    payload = {
        "username": USERNAME,
        "password": PASSWORD,
        "execution": execution,
        "_eventId": event_id,
        "submit": "登录",
        "type": "username_password"
    }
    
    print("🚀 [2/4] 发送账号密码...")
    # 这一步请求 sso，成功后会返回 302 跳转，requests 默认会自动跟随跳转
    # 我们需要它自动跟随，因为它会跳转到 classroom.../login?ticket=...
    # 并在那个页面被服务器种下 Cookie
    login_resp = session.post(LOGIN_URL, data=payload)
    
    # 检查是否到了 classroom 域名
    current_url = login_resp.url
    print(f"   当前 URL: {current_url}")
    
    # 检查 Cookie 是否存在
    # 我们重点找 '_token' 这个 cookie
    cookies = session.cookies.get_dict()
    if '_token' in cookies:
        print("   ✅ 登录成功！已获取 _token Cookie。")
        # 打印一下看看是不是和浏览器里一样长
        print(f"   Cookie 长度: {len(cookies['_token'])}")
        return True
    else:
        # 如果 URL 里有 ticket 但没有 cookie，可能脚本没自动跳转，手动访问一下
        if "ticket=" in current_url:
            print("   ⚠️ 发现 Ticket 但未获取 Cookie，尝试手动激活...")
            session.get(current_url)
            if '_token' in session.cookies.get_dict():
                print("   ✅ 补救成功！Cookie 已获取。")
                return True
        
        print("   ❌ 登录失败：未获取到有效 Cookie。")
        print("   调试信息 - 当前 Cookie:", cookies)
        return False

def get_course_info(url):
    print("🚀 [3/4] 解析课程信息...")
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    c_id = params.get('course_id', [None])[0]
    s_id = params.get('sub_id', [None])[0]
    
    api_url = f"https://classroom.msa.buaa.edu.cn/courseapi/v3/portal-home-setting/get-sub-info?course_id={c_id}&sub_id={s_id}"
    
    # 此时请求会自动带上 Cookie
    resp = session.get(api_url)
    
    try:
        data = resp.json()
    except:
        print(f"   ❌ API 响应非 JSON，可能 Cookie 无效。")
        return None, None, None

    if data.get('code') != 0:
        print(f"   ❌ API 报错: {data.get('msg')}")
        return None, None, None
        
    info = data['data']
    guid = info.get('resource_guid')
    title = info.get('sub_title', 'PPT_Export').strip()
    title = "".join([c for c in title if c.isalnum() or c in (' ', '-', '_')])
    
    return c_id, s_id, guid, title

def download_ppt(c_id, s_id, guid, title):
    print("🚀 [4/4] 下载 PPT...")
    api_url = f"https://classroom.msa.buaa.edu.cn/pptnote/v1/schedule/search-ppt?course_id={c_id}&sub_id={s_id}&page=1&per_page=500&resource_guid={guid}"
    
    resp = session.get(api_url)
    data = resp.json()
    
    slide_urls = []
    if data.get('list'):
        for item in data['list']:
            try:
                c = json.loads(item['content'])
                if c.get('pptimgurl'): slide_urls.append(c['pptimgurl'])
            except: continue

    if not slide_urls:
        print("   ⚠️ 未找到图片")
        return

    temp_dir = "temp_slides_final"
    if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    files = []
    print(f"   📄 开始下载 {len(slide_urls)} 张图片...")
    for i, url in enumerate(slide_urls):
        fname = os.path.join(temp_dir, f"{i:03d}.jpg")
        r = requests.get(url) # 图片一般不需要 Cookie，但带上也无妨
        with open(fname, 'wb') as f: f.write(r.content)
        files.append(fname)
        print(f"\r   ⬇️ {i+1}/{len(slide_urls)}", end="")
        
    print(f"\n   📦 合成 PDF: {title}.pdf")
    with open(f"{title}.pdf", "wb") as f:
        f.write(img2pdf.convert(files))
    shutil.rmtree(temp_dir)
    print("✅ 完成！")

if __name__ == "__main__":
    if auto_login():
        res = get_course_info(TARGET_COURSE_URL)
        if res and res[0]:
            download_ppt(*res)