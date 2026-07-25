import os
import sys
from urllib.parse import urlparse
import pacparser


def test_pac_file(pac_path, target_url):
    """使用 pacparser 驗證本地 PAC 檔案對特定 URL 的解析結果。"""
    # 檢查 PAC 檔案是否存在
    if not os.path.exists(pac_path):
        print(f"\n[-] 錯誤：找不到 PAC 檔案，請確認路徑是否正確：{pac_path}")
        return

    # 從 URL 中自動切出 host
    parsed_url = urlparse(target_url)
    target_host = parsed_url.hostname
    if not target_host:
        print(
            f"\n[-] 錯誤：無法從網址中解析出 Hostname，請檢查網址格式（需包含 http:// 或 https://）。"
        )
        return

    print(f"\n[+] 正在初始化 PAC 引擎...")
    pacparser.init()

    try:
        print(f"[+] 正在載入 PAC 檔案: {pac_path}")
        pacparser.parse_file(pac_path)

        print(f"[+] 開始比對路由...")
        print(f"    目標網址: {target_url}")
        print(f"    目標主機: {target_host}")
        print("-" * 60)

        # 執行 PAC 檔案內部的 FindProxyForURL 邏輯
        result = pacparser.find_proxy(target_url, target_host)

        # 印出綠色高亮的解析結果
        print(f"[+] 解析結果：\033[92m{result}\033[0m")
        print("-" * 60)

    except Exception as e:
        print(f"\n[-] 解析過程中發生錯誤：{e}")
        print(
            "[-] 這通常代表 PAC 檔案內部的 JavaScript 語法有誤，或使用了不支援的函式。"
        )

    finally:
        # 釋放 pacparser 佔用的記憶體資源
        pacparser.cleanup()


if __name__ == "__main__":
    # 定義預設值，直接按 Enter 就會自動帶入
    DEFAULT_PAC = r"C:\temp\autoproxy\shaproxy_zs.pac"
    DEFAULT_URL = "https://nomuracmdbqa.service-now.com/now/nav/ui/home"

    print("=" * 60)
    print(" PAC 檔案路徑與路由測試工具")
    print("=" * 60)

    # 詢問 PAC 檔案路徑
    user_pac = input(f"請輸入 PAC 檔案路徑 [{DEFAULT_PAC}]: ").strip()
    if not user_pac:
        user_pac = DEFAULT_PAC
    # 移除使用者不小心複製到的前後雙引號
    user_pac = user_pac.strip('"')

    # 詢問測試網址
    user_url = input(f"請輸入要測試的網址 [{DEFAULT_URL}]: ").strip()
    if not user_url:
        user_url = DEFAULT_URL
    user_url = user_url.strip('"')

    # 執行測試
    test_pac_file(user_pac, user_url)

    # 測試完成後暫停，避免 CMD 視窗直接關閉
    print("\n測試結束。")
    input("按任意鍵退出...")