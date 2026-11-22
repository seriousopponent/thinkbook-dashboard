#!/usr/bin/python3
"""ThinkBook Dashboard: a local React UI inside a Qt desktop window."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys

# This utility does not need GPU compositing or WebGL. Avoid waking the dGPU
# just to draw its own dashboard, and keep Chromium's sandbox enabled.
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu --disable-background-networking')

from PyQt6.QtCore import QObject, QUrl, Qt, pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtGui import QIcon, QDesktopServices
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineUrlRequestInterceptor
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6 import sip

from service import DashboardService

BASE = Path(__file__).resolve().parent
DIST = BASE / 'ui/dist'


class LocalRequests(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        url = info.requestUrl()
        if url.scheme() == 'file':
            try:
                Path(url.toLocalFile()).resolve().relative_to(DIST)
            except ValueError:
                info.block(True)
        elif url.scheme() not in ('qrc', 'data', 'blob'):
            info.block(True)


class LocalPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        if is_main_frame and url.scheme() == 'https' and navigation_type == self.NavigationType.NavigationTypeLinkClicked:
            QDesktopServices.openUrl(url)
            return False
        return url.scheme() in ('file', 'qrc', 'data', 'about')


class Bridge(QObject):
    reply = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.service = DashboardService()
        self.executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='dashboard')
        self.inflight = set()
        self.readonly = False

    @pyqtSlot(str, str, str)
    def request(self, request_id, action, payload):
        if self.readonly and action not in ('status', 'diagnostics'):
            self.reply.emit(request_id, json.dumps(dict(ok=False, error='Görünüm testi sırasında ayarlar değiştirilemez.')))
            return
        if len(payload) > 4096 or len(self.inflight) >= 8 or action in self.inflight:
            self.reply.emit(request_id, json.dumps(dict(ok=False, error='Bir işlem zaten sürüyor.')))
            return
        try:
            data = json.loads(payload)
        except ValueError:
            self.reply.emit(request_id, json.dumps(dict(ok=False, error='Geçersiz istek.')))
            return
        self.inflight.add(action)

        def finished(future):
            try:
                result = dict(ok=True, data=future.result())
            except Exception as error:
                result = dict(ok=False, error=str(error))
            self.inflight.discard(action)
            self.reply.emit(request_id, json.dumps(result, ensure_ascii=False))

        self.executor.submit(self.service.run, action, data).add_done_callback(finished)

    @pyqtSlot(str)
    def copyText(self, text):
        if len(text) <= 65536:
            QApplication.clipboard().setText(text)


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('ThinkBook Dashboard')
        self.setWindowIcon(QIcon(str(BASE / 'icon.svg')))
        self.resize(1180, 850)
        self.setMinimumSize(760, 600)
        self.profile = QWebEngineProfile('thinkbook-dashboard', self)
        self.profile.setPersistentStoragePath(str(Path.home() / '.local/state/thinkbook-dashboard/web-profile'))
        self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        self.interceptor = LocalRequests(self)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.view = QWebEngineView(self)
        self.page = LocalPage(self.profile, self.view)
        self.view.setPage(self.page)
        for attribute in ('WebGLEnabled', 'LocalContentCanAccessRemoteUrls', 'JavascriptCanOpenWindows'):
            self.page.settings().setAttribute(getattr(QWebEngineSettings.WebAttribute, attribute), False)
        self.channel = QWebChannel(self.page)
        self.bridge = Bridge(self)
        self.channel.registerObject('dashboard', self.bridge)
        self.page.setWebChannel(self.channel)
        self.setCentralWidget(self.view)
        self.view.load(QUrl.fromLocalFile(str(DIST / 'index.html')))

    def focus(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if self.bridge.service.busy:
            QMessageBox.information(self, 'Ayar uygulanıyor', 'Ayar işlemi tamamlanınca pencereyi kapatabilirsin.')
            event.ignore()
            return
        self.bridge.executor.shutdown(wait=False, cancel_futures=True)
        event.accept()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--smoke-test', action='store_true', help='Open, validate bridge, save a screenshot, then close.')
    args = parser.parse_args()
    if args.probe:
        print(json.dumps(DashboardService().status(), ensure_ascii=False, indent=2))
        return 0
    app = QApplication(sys.argv[:1])
    app.setApplicationName('ThinkBook Dashboard')
    app.setDesktopFileName('io.github.thinkbook.Dashboard')
    server_name = 'thinkbook-dashboard-v2-' + str(os.getuid()) + ('-test' if args.smoke_test else '')
    socket = QLocalSocket()
    socket.connectToServer(server_name)
    if socket.waitForConnected(200):
        socket.write(b'focus')
        socket.waitForBytesWritten(200)
        return 0
    QLocalServer.removeServer(server_name)
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen(server_name):
        raise RuntimeError('Dashboard yerel oturumu açılamadı.')
    if not (DIST / 'index.html').is_file():
        QMessageBox.critical(None, 'Arayüz bulunamadı', 'Arayüz dosyaları eksik. ui klasöründe npm run build çalıştırılmalı.')
        return 1
    window = Window()

    def activate():
        connection = server.nextPendingConnection()
        if connection:
            connection.close()
        window.focus()

    server.newConnection.connect(activate)
    window.show()
    if args.smoke_test:
        window.bridge.readonly = True
        def check():
            def finished(value):
                print(json.dumps(value, ensure_ascii=False), flush=True)
                window.grab().save('/tmp/thinkbook-dashboard-native.png')
                app.exit(0 if value and value.get('connected') else 1)
            window.page.runJavaScript("({connected: document.body.dataset.connected === 'true', title: document.title, text: document.body.innerText.slice(0,2000)})", finished)
        QTimer.singleShot(6000, check)
    result = app.exec()
    window.bridge.executor.shutdown(wait=True, cancel_futures=True)
    sip.delete(window.view)
    sip.delete(window.profile)
    server.close()
    return result


if __name__ == '__main__':
    raise SystemExit(main())
