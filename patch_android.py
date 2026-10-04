import glob, re

java_files = glob.glob("android/app/src/main/java/**/MainActivity.java", recursive=True) + glob.glob("app/src/main/java/**/MainActivity.java", recursive=True)
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
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.media.MediaScannerConnection;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;
import com.getcapacitor.BridgeActivity;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import org.json.JSONObject;

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
                WebView wv = this.bridge.getWebView();
                wv.getSettings().setMediaPlaybackRequiresUserGesture(false);
                wv.addJavascriptInterface(new AndroidNativeBridge(), "AndroidNative");
                wv.reload();
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

    private byte[] readAllBytes(InputStream is) throws Exception {{
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        byte[] data = new byte[16384];
        int nRead;
        while ((nRead = is.read(data, 0, data.length)) != -1) {{
            buffer.write(data, 0, nRead);
        }}
        return buffer.toByteArray();
    }}

    public class AndroidNativeBridge {{
        @JavascriptInterface
        public String getClipboard() {{
            String live = readSystemClip();
            return live != null ? live : "";
        }}

        @JavascriptInterface
        public String resolveRedirect(String urlStr) {{
            try {{
                HttpURLConnection conn = (HttpURLConnection) new URL(urlStr).openConnection();
                conn.setInstanceFollowRedirects(true);
                conn.setConnectTimeout(10000);
                conn.setReadTimeout(10000);
                conn.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/124.0.0.0 Mobile Safari/537.36");
                conn.connect();
                String finalUrl = conn.getURL().toString();
                conn.disconnect();
                return finalUrl;
            }} catch (Exception e) {{
                return urlStr;
            }}
        }}

        @JavascriptInterface
        public String httpGet(String urlStr, String headersJson) {{
            try {{
                HttpURLConnection conn = (HttpURLConnection) new URL(urlStr).openConnection();
                conn.setInstanceFollowRedirects(true);
                conn.setRequestMethod("GET");
                conn.setConnectTimeout(12000);
                conn.setReadTimeout(12000);
                conn.setRequestProperty("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36");
                if (headersJson != null && !headersJson.isEmpty()) {{
                    JSONObject obj = new JSONObject(headersJson);
                    Iterator<String> keys = obj.keys();
                    while (keys.hasNext()) {{
                        String k = keys.next();
                        conn.setRequestProperty(k, obj.optString(k, ""));
                    }}
                }}
                InputStream is = conn.getResponseCode() >= 400 ? conn.getErrorStream() : conn.getInputStream();
                if (is == null) return "";
                byte[] bytes = readAllBytes(is);
                is.close();
                return new String(bytes, StandardCharsets.UTF_8);
            }} catch (Exception e) {{
                return "";
            }}
        }}

        @JavascriptInterface
        public String httpPost(String urlStr, String bodyStr, String headersJson) {{
            try {{
                HttpURLConnection conn = (HttpURLConnection) new URL(urlStr).openConnection();
                conn.setInstanceFollowRedirects(true);
                conn.setRequestMethod("POST");
                conn.setDoOutput(true);
                conn.setConnectTimeout(12000);
                conn.setReadTimeout(12000);
                conn.setRequestProperty("Content-Type", "application/json");
                if (headersJson != null && !headersJson.isEmpty()) {{
                    JSONObject obj = new JSONObject(headersJson);
                    Iterator<String> keys = obj.keys();
                    while (keys.hasNext()) {{
                        String k = keys.next();
                        conn.setRequestProperty(k, obj.optString(k, ""));
                    }}
                }}
                if (bodyStr != null) {{
                    try (OutputStream os = conn.getOutputStream()) {{
                        os.write(bodyStr.getBytes(StandardCharsets.UTF_8));
                        os.flush();
                    }}
                }}
                InputStream is = conn.getResponseCode() >= 400 ? conn.getErrorStream() : conn.getInputStream();
                if (is == null) return "";
                byte[] bytes = readAllBytes(is);
                is.close();
                return new String(bytes, StandardCharsets.UTF_8);
            }} catch (Exception e) {{
                return "";
            }}
        }}

        @JavascriptInterface
        public String fetchMediaBase64(String urlStr) {{
            try {{
                HttpURLConnection conn = (HttpURLConnection) new URL(urlStr).openConnection();
                conn.setInstanceFollowRedirects(true);
                conn.setConnectTimeout(15000);
                conn.setReadTimeout(30000);
                if (urlStr.contains("googlevideo.com")) {{
                    conn.setRequestProperty("User-Agent", "com.google.android.apps.youtube.vr.oculus/1.56.21 (Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip");
                }} else {{
                    conn.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/124.0.0.0 Mobile Safari/537.36");
                }}
                InputStream is = conn.getInputStream();
                byte[] bytes = readAllBytes(is);
                is.close();
                return Base64.encodeToString(bytes, Base64.NO_WRAP);
            }} catch (Exception e) {{
                return "";
            }}
        }}

        @JavascriptInterface
        public boolean saveBase64(String b64, String filename, String mimeType) {{
            try {{
                int comma = b64.indexOf(',');
                String pure = comma >= 0 ? b64.substring(comma + 1) : b64;
                byte[] bytes = Base64.decode(pure, Base64.DEFAULT);
                boolean isAudio = (mimeType != null && mimeType.startsWith("audio")) || filename.toLowerCase().endsWith(".mp3");
                String finalMime = isAudio ? "audio/mpeg" : "video/mp4";

                if (Build.VERSION.SDK_INT >= 29) {{
                    ContentResolver resolver = getContentResolver();
                    ContentValues values = new ContentValues();
                    values.put(MediaStore.MediaColumns.DISPLAY_NAME, filename);
                    values.put(MediaStore.MediaColumns.MIME_TYPE, finalMime);
                    values.put(
                        MediaStore.MediaColumns.RELATIVE_PATH,
                        (isAudio ? Environment.DIRECTORY_MUSIC : Environment.DIRECTORY_MOVIES) + "/MediaLoader"
                    );
                    values.put(MediaStore.MediaColumns.IS_PENDING, 1);

                    Uri collection = isAudio
                        ? MediaStore.Audio.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
                        : MediaStore.Video.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY);

                    Uri itemUri = resolver.insert(collection, values);
                    if (itemUri != null) {{
                        try (OutputStream os = resolver.openOutputStream(itemUri)) {{
                            if (os != null) {{
                                os.write(bytes);
                                os.flush();
                            }}
                        }}
                        ContentValues doneValues = new ContentValues();
                        doneValues.put(MediaStore.MediaColumns.IS_PENDING, 0);
                        resolver.update(itemUri, doneValues, null, null);
                        return true;
                    }}
                }}

                File pubDir = Environment.getExternalStoragePublicDirectory(
                    isAudio ? Environment.DIRECTORY_MUSIC : Environment.DIRECTORY_MOVIES
                );
                File dir = new File(pubDir, "MediaLoader");
                if (!dir.exists()) dir.mkdirs();
                File outFile = new File(dir, filename);
                try (FileOutputStream fos = new FileOutputStream(outFile)) {{
                    fos.write(bytes);
                    fos.flush();
                }}
                MediaScannerConnection.scanFile(
                    MainActivity.this,
                    new String[]{{ outFile.getAbsolutePath() }},
                    new String[]{{ finalMime }},
                    null
                );
                return true;
            }} catch (Exception e) {{
                return false;
            }}
        }}

        @JavascriptInterface
        public void downloadUrl(String url, String filename) {{
            try {{
                boolean isAudio = filename != null && filename.toLowerCase().endsWith(".mp3");
                DownloadManager.Request req = new DownloadManager.Request(Uri.parse(url));
                req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                req.setTitle(filename);
                req.setMimeType(isAudio ? "audio/mpeg" : "video/mp4");
                req.allowScanningByMediaScanner();
                req.setDestinationInExternalPublicDir(
                    isAudio ? Environment.DIRECTORY_MUSIC : Environment.DIRECTORY_MOVIES,
                    "MediaLoader/" + filename
                );
                DownloadManager dm = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
                if (dm != null) dm.enqueue(req);
            }} catch (Exception ignored) {{}}
        }}
    }}
}}
"""
    with open(jpath, "w", encoding="utf-8") as f:
        f.write(new_java)
