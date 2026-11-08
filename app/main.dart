import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';

// يُمرَّر اسم المتجر عند البناء: --dart-define=SLUG=eret
const String kSlug = String.fromEnvironment('SLUG', defaultValue: '');
const String kHost = 'https://dukaan.art';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(SystemUiOverlayStyle.dark);
  runApp(const StoreApp());
}

class StoreApp extends StatelessWidget {
  const StoreApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
        debugShowCheckedModeBanner: false,
        home: const StorePage(),
      );
}

class StorePage extends StatefulWidget {
  const StorePage({super.key});
  @override
  State<StorePage> createState() => _StorePageState();
}

class _StorePageState extends State<StorePage> {
  late final WebViewController _c;
  bool _loading = true;
  bool _first = true; // شاشة بيضاء نظيفة حتى يجهز أول تحميل
  bool _failed = false;
  String? _tok; // رمز الإشعارات (Firebase)

  Uri get _home => Uri.parse(kSlug.isEmpty ? kHost : '$kHost/$kSlug?app=1');

  void _injectToken() {
    final t = _tok;
    if (t == null || !RegExp(r'^[A-Za-z0-9_:\-]+$').hasMatch(t)) return;
    _c.runJavaScript("window.__dukfcm='$t';window.dispatchEvent(new Event('dukfcm'));");
  }

  void _dbg(String m) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(m), duration: const Duration(seconds: 12)));
  }

  String get _topic => 's_' + kSlug.toLowerCase().replaceAll(RegExp(r'[^a-z0-9_\-]'), '_');

  Future<void> _initPush() async {
    String step = 'init';
    try {
      await Firebase.initializeApp();
      step = 'permission';
      final m = FirebaseMessaging.instance;
      await m.requestPermission();
      step = 'topic';
      if (kSlug.isNotEmpty) await m.subscribeToTopic(_topic);
      step = 'token';
      _tok = await m.getToken();
      if (_tok == null) _dbg('DBG token NULL');
    } catch (e) {
      _dbg('DBG error at $step: $e');
    }
  }

  @override
  void initState() {
    super.initState();
    _initPush();
    _c = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(NavigationDelegate(
        onPageStarted: (_) => setState(() { _loading = true; _failed = false; }),
        onPageFinished: (_) {
          _c.runJavaScript(
              "(function(){var s=document.createElement('style');s.textContent='html,body{-webkit-tap-highlight-color:transparent;overscroll-behavior:none}body{-webkit-user-select:none;user-select:none}input,textarea{-webkit-user-select:text;user-select:text}';document.head.appendChild(s);})()");
          setState(() { _loading = false; _first = false; });
        },
        onWebResourceError: (e) {
          if (e.isForMainFrame ?? true) setState(() { _failed = true; _loading = false; });
        },
        onNavigationRequest: (r) {
          final u = Uri.tryParse(r.url);
          if (u == null) return NavigationDecision.prevent;
          // روابط واتساب والاتصال وغيرها تُفتح خارج التطبيق
          if (u.scheme != 'https' && u.scheme != 'http') {
            launchUrl(u, mode: LaunchMode.externalApplication);
            return NavigationDecision.prevent;
          }
          if (u.host == 'wa.me' || u.host.endsWith('whatsapp.com')) {
            launchUrl(u, mode: LaunchMode.externalApplication);
            return NavigationDecision.prevent;
          }
          return NavigationDecision.navigate;
        },
      ))
      ..setBackgroundColor(Colors.white)
      ..loadRequest(_home);
    _c.enableZoom(false);
    final p = _c.platform;
    if (p is AndroidWebViewController) {
      p.setOnPlatformPermissionRequest((req) async {
        final wantsCam = req.types.contains(WebViewPermissionResourceType.camera);
        if (wantsCam) {
          final st = await Permission.camera.request();
          if (st.isGranted) { await req.grant(); } else { await req.deny(); }
        } else {
          await req.deny();
        }
      });
      p.setGeolocationPermissionsPromptCallbacks(
        onShowPrompt: (params) async {
          final st = await Permission.locationWhenInUse.request();
          final ok = st.isGranted;
          return GeolocationPermissionsResponse(allow: ok, retain: ok);
        },
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) async {
        if (didPop) return;
        if (await _c.canGoBack()) {
          _c.goBack();
        } else {
          SystemNavigator.pop();
        }
      },
      child: Scaffold(
        backgroundColor: Colors.white,
        body: SafeArea(
          child: Stack(children: [
            WebViewWidget(controller: _c),
            if (_first)
              Container(color: Colors.white, alignment: Alignment.center, child: const CircularProgressIndicator()),
            if (_loading && !_first) const LinearProgressIndicator(minHeight: 3),
            if (_failed)
              Container(
                color: Colors.white,
                alignment: Alignment.center,
                child: Directionality(
                  textDirection: TextDirection.rtl,
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                    const Text('تعذّر الاتصال بالمتجر', style: TextStyle(fontSize: 18)),
                    const SizedBox(height: 12),
                    ElevatedButton(onPressed: () => _c.loadRequest(_home), child: const Text('إعادة المحاولة')),
                  ]),
                ),
              ),
          ]),
        ),
      ),
    );
  }
}
