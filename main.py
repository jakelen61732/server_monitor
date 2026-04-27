import threading
import os

try:
    from gevent import monkey
    # gevent monkey patching must happen before importing Flask/SocketIO
    if platform == 'android':
        monkey.patch_all(thread=False)
    else:
        monkey.patch_all()
except ImportError:
    pass

from server_monitor import app, socketio, SERVER_HOST, SERVER_PORT
from monitor_core.utils import ensure_port_available
from kivy.app import App
from kivy.uix.label import Label
from kivy.utils import platform
from kivy.clock import Clock
from kivy.logger import Logger

class ServerMonitorApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.active_port = SERVER_PORT

    def build(self):
        """Starts the Flask server and prepares the UI."""
        # Ensure the port is available on the device
        self.active_port = ensure_port_available("127.0.0.1", SERVER_PORT)
        
        def run_flask():
            try:
                Logger.info(f"Flask: Starting server on 127.0.0.1:{self.active_port}")
                socketio.run(
                    app, host="127.0.0.1", port=self.active_port, debug=False, use_reloader=False
                )
            except ImportError as e:
                Logger.error(f"Flask: Missing dependency: {str(e)}")
            except Exception as e:
                Logger.error(f"Flask: Server crashed: {str(e)}")

        # 1. Start the Flask-SocketIO server in a background daemon thread
        # For APK usage, we default to 127.0.0.1 for security within the sandbox
        flask_thread = threading.Thread(
            target=run_flask,
            daemon=True
        )
        flask_thread.start()

        # 2. UI Logic
        if platform == 'android':
            # On Android, we wait a moment for the server to start, then inject the WebView
            Clock.schedule_once(self.create_android_webview, 2)
            return Label(text="Initializing Monitor Service...")
        else:
            # Desktop fallback for testing
            return Label(text=f"Server running at http://127.0.0.1:{self.active_port}\nWebView is only initialized on Android.")

    def create_android_webview(self, *args):
        """Uses PyJnius to create a native Android WebView as the app content."""
        Logger.info("WebView: Initializing native Android components")
        try:
            from jnius import autoclass
            from android.runnable import run_on_ui_thread

            # Access native Android Java classes
            try:
                WebView = autoclass('android.webkit.WebView')
                WebViewClient = autoclass('android.webkit.WebViewClient')
                WebSettings = autoclass('android.webkit.WebSettings')
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                activity = PythonActivity.mActivity
            except Exception as jni_e:
                Logger.error(f"WebView: JNI class lookup failed: {str(jni_e)}")
                return

            @run_on_ui_thread
            def set_webview_as_content():
                try:
                    webview = WebView(activity)
                    settings = webview.getSettings()
                    settings.setJavaScriptEnabled(True)
                    settings.setDomStorageEnabled(True) 
                    settings.setAllowFileAccess(True)
                    
                    webview.setWebViewClient(WebViewClient())
                    activity.setContentView(webview)
                    webview.loadUrl(f"http://127.0.0.1:{self.active_port}")
                    Logger.info("WebView: Successfully initialized and loaded URL")
                except Exception as e:
                    Logger.error(f"WebView: JNI error in UI thread: {str(e)}")

            set_webview_as_content()
        except Exception as e:
            print(f"Native WebView error: {e}")
            Logger.error(f"WebView: Failed to setup Jnius classes: {str(e)}")

if __name__ == '__main__':
    ServerMonitorApp().run()
