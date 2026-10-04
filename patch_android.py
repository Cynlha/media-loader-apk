import os, re, glob

root = os.environ.get("GITHUB_WORKSPACE", ".")

gradle_path = os.path.join(root, "android/app/build.gradle")
if os.path.exists(gradle_path):
    with open(gradle_path, "r", encoding="utf-8") as f:
        g = f.read()
    g = re.sub(r'versionName\s+"[^"]+"', 'versionName "0.11 BETA"', g)
    with open(gradle_path, "w", encoding="utf-8") as f:
        f.write(g)

manifest_path = os.path.join(root, "android/app/src/main/AndroidManifest.xml")
if os.path.exists(manifest_path):
    with open(manifest_path, "r", encoding="utf-8") as f:
        m = f.read()
    if "usesCleartextTraffic" not in m:
        m = m.replace("<application", '<application android:usesCleartextTraffic="true"', 1)
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(m)

java_files = glob.glob(os.path.join(root, "android/app/src/main/java/**/MainActivity.java"), recursive=True)
if java_files:
    jpath = java_files[0]
    with open(jpath, "r", encoding="utf-8") as f:
        orig = f.read()
    pkg_match = re.search(r"package\s+([a-zA-Z0-9_.]+)\s*;", orig)
    pkg = pkg_match.group(1) if pkg_match else "com.termux.medialoader"

    new_java = f"""package {pkg};

import android.app.DownloadManager;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.webkit.JavascriptInterface;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {{
    private volatile String cachedClip = "";

    private String readSystemClip() {{
        try {{
            ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            if (cm != null && cm.hasPrimaryClip()) {{
                ClipData clip = cm.getPrimaryClip();
                if (clip != null && clip.getItemCount() > 0) {{
                    CharSequence txt = clip.getItemAt(0).coerceToText(this);
                    if (txt != null && txt.length() > 0) {{
                        cachedClip = txt.toString();
                        return cachedClip;
                    }}
                }}
            }}
        }} catch (Exception ignored) {{}}
        return cachedClip;
    }}

    @Override
    public void onCreate(Bundle savedInstanceState) {{
        super.onCreate(savedInstanceState);
        try {{
            if (this.bridge != null && this.bridge.getWebView() != null) {{
                this.bridge.getWebView().addJavascriptInterface(new AndroidNativeBridge(), "AndroidNative");
            }}
        }} catch (Exception ignored) {{}}
    }}

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {{
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {{
            readSystemClip();
        }}
    }}

    public class AndroidNativeBridge {{
        @JavascriptInterface
        public String getClipboard() {{
            String live = readSystemClip();
            return live != null ? live : "";
        }}

        @JavascriptInterface
        public void downloadUrl(String url, String filename) {{
            try {{
                DownloadManager.Request req = new DownloadManager.Request(Uri.parse(url));
                req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                req.setTitle(filename);
                req.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, "MediaLoader/" + filename);
                DownloadManager dm = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
                if (dm != null) dm.enqueue(req);
            }} catch (Exception ignored) {{}}
        }}
    }}
}}
"""
    with open(jpath, "w", encoding="utf-8") as f:
        f.write(new_java)
