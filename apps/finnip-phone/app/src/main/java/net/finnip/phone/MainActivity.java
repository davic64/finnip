package net.finnip.phone;

import android.Manifest;
import android.app.Activity;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.BatteryManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.util.Arrays;

/** Finnip on an old Android phone: the web app (?phone=1) full screen, always listening, like an Echo
 *  with a screen. The screen never turns off; the page dims it at rest through FinnipPhone.dim(). */
public class MainActivity extends Activity {
    private static final String HOST = Uri.parse(BuildConfig.FINNIP_URL).getHost();
    private static final String PAGE = BuildConfig.FINNIP_URL + "/?phone=1";
    private static final float DIM = 0.01f;   // window brightness at rest (0..1); the system's own otherwise
    private static final long RETRY_MS = 5000; // no connection to the gateway: load again
    private static final int[] LOW_BATTERY = {10, 5}; // % at which Finnip asks to be charged, once each
    private static final String OFFLINE = "<body style='margin:0;height:100vh;display:grid;place-items:center;"
            + "background:#000;color:#4aa8ff;font:12px monospace;letter-spacing:.28em'>"
            + "SIN CONEXIÓN CON FINNIP · REINTENTANDO</body>";

    private final Handler main = new Handler(Looper.getMainLooper());
    private WebView web;
    private int warnedAt = 101; // lowest LOW_BATTERY level already announced on this discharge

    /** Battery level changes: at 10 % and 5 % without a charger, Finnip says so out loud. */
    private final BroadcastReceiver battery = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            int level = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
            int scale = intent.getIntExtra(BatteryManager.EXTRA_SCALE, 100);
            if (level < 0 || scale <= 0) return;
            if (intent.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) != 0) {
                warnedAt = 101;
                return;
            }
            int pct = level * 100 / scale;
            for (int threshold : LOW_BATTERY) {
                if (pct <= threshold && warnedAt > threshold) {
                    warnedAt = threshold;
                    web.evaluateJavascript("window.finnipBattery && window.finnipBattery(" + pct + ")", null);
                    break;
                }
            }
        }
    };

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        // Draw under the camera hole too (it sits on a short edge when the phone lies on its side).
        getWindow().getAttributes().layoutInDisplayCutoutMode =
                WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;
        web = new WebView(this);
        web.setBackgroundColor(Color.BLACK);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setMediaPlaybackRequiresUserGesture(false); // Finnip speaks without a tap first
        web.addJavascriptInterface(new Bridge(), "FinnipPhone");
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest request) {
                // Only Finnip's own page gets the microphone, and nothing else (no camera).
                boolean ours = HOST != null && HOST.equals(request.getOrigin().getHost());
                if (ours && Arrays.asList(request.getResources()).contains(PermissionRequest.RESOURCE_AUDIO_CAPTURE))
                    request.grant(new String[] {PermissionRequest.RESOURCE_AUDIO_CAPTURE});
                else
                    request.deny();
            }
        });
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return !HOST.equals(request.getUrl().getHost()); // links elsewhere go nowhere
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    view.loadDataWithBaseURL(null, OFFLINE, "text/html", "utf-8", null);
                    main.removeCallbacksAndMessages(null);
                    main.postDelayed(() -> web.loadUrl(PAGE), RETRY_MS);
                }
            }
        });
        setContentView(web);
        registerReceiver(battery, new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
        fullScreen();
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED)
            web.loadUrl(PAGE);
        else
            requestPermissions(new String[] {Manifest.permission.RECORD_AUDIO}, 1);
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] permissions, int[] results) {
        web.loadUrl(PAGE); // without the permission the page says so itself
    }

    @SuppressWarnings("deprecation")
    private void fullScreen() {
        web.setSystemUiVisibility(View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY | View.SYSTEM_UI_FLAG_FULLSCREEN
                | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN);
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) fullScreen();
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        // Kiosk: back never leaves Finnip.
    }

    @Override
    protected void onDestroy() {
        main.removeCallbacksAndMessages(null);
        unregisterReceiver(battery);
        web.destroy();
        super.onDestroy();
    }

    /** Called by the page (window.FinnipPhone). */
    private class Bridge {
        @JavascriptInterface
        public void dim(boolean on) {
            main.post(() -> {
                WindowManager.LayoutParams params = getWindow().getAttributes();
                params.screenBrightness = on ? DIM : WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE;
                getWindow().setAttributes(params);
            });
        }
    }
}
