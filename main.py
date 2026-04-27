import threading
import os
from gevent import monkey

# gevent monkey patching must happen before importing Flask/SocketIO
monkey.patch_all(thread=False)

from server_monitor import app, socketio, SERVER_HOST, SERVER_PORT
from monitor_core.utils import ensure_port_available
from kivy.app import App
from kivy.uix.label import Label
from kivy.utils import platform
from kivy.clock import Clock

class ServerMonitorApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.active_port = SERVER_PORT

    def build(self):
        """Starts the Flask server and prepares the UI."""
        # Ensure the port is available on the device
        self.active_port = ensure_port_available("127.0.0.1", SERVER_PORT)
        
        # 1. Start the Flask-SocketIO server in a background daemon thread
        # For APK usage, we default to 127.0.0.1 for security within the sandbox
        flask_thread = threading.Thread(
            target=lambda: socketio.run(
                app, host="127.0.0.1", port=self.active_port, debug=False, use_reloader=False
            ),
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
        try:
            from jnius import autoclass
            from android.runnable import run_on_ui_thread

            # Access native Android Java classes
            WebView = autoclass('android.webkit.WebView')
            WebViewClient = autoclass('android.webkit.WebViewClient')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity

            @run_on_ui_thread
            def set_webview_as_content():
                webview = WebView(activity)
                settings = webview.getSettings()
                settings.setJavaScriptEnabled(True)
                settings.setDomStorageEnabled(True) # Required for some JS charts
                settings.setAllowFileAccess(True)
                
                webview.setWebViewClient(WebViewClient())
                activity.setContentView(webview)
                webview.loadUrl(f"http://127.0.0.1:{self.active_port}")

            set_webview_as_content()
        except Exception as e:
            print(f"Native WebView error: {e}")

if __name__ == '__main__':
    ServerMonitorApp().run()
