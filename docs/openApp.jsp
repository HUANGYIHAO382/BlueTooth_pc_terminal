<%@ page language="java" import="java.util.*" pageEncoding="UTF-8"%>
<%@ page import="com.huawei.iptvmw.epg.bean.info.UserProfile"%>
<%@ page import="com.huawei.iptvmw.epg.bean.MetaData"%>
<%@ include file="../../../hwdatajsp/checkReport.jsp" %>
<%
String path = request.getContextPath();
String basePath = request.getScheme()+"://"+request.getServerName()+":"+request.getServerPort()+path+"/";
UserProfile userProfile = new UserProfile(request);
String userId = userProfile.getUserId();
String url = request.getRequestURI().replace("specialarea/yishiteng/openApp.jsp","");
String sessionId = session.getId();
String returnurl = request.getParameter("returnurl") == null ? "" : request.getParameter("returnurl");
%>

<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
  <head>

  <script src="../../../js/report.js"></script>
  <script src="../../../js/WkEpg.js"></script>
  <script type="text/javascript" src="../../../config/config.js"></script>
    <base href="<%=basePath%>">

    <title>家庭健康APK拉起</title>
	<meta http-equiv="pragma" content="no-cache">
	<meta http-equiv="cache-control" content="no-cache">
	<meta http-equiv="expires" content="0">
	<meta http-equiv="keywords" content="keyword1,keyword2,keyword3">
	<meta http-equiv="description" content="EPG拉起家庭健康APK">

	<script type="text/javascript">
	<jsp:include page="../../../util/passwordEncryption.jsp">
		<jsp:param name="varName" value="encryurID" />
		<jsp:param name="userID" value="<%=userId%>" />
		<jsp:param name="isJson" value="1" />
	</jsp:include>

		// ============================================================
		// 【部署前必改】APK 与应用商城配置（三处必须与 APK 一致）
		// ============================================================

		// 你的 APK 包名（与 build.gradle 的 applicationId 一致）
		// 方案A：com.example.myapplication
		// 方案B（本仓库默认）：com.iknet.bloodmeasuredemo
		var APP_PACKAGE = "com.iknet.bloodmeasuredemo";

		// 启动 Activity 全类名（与 AndroidManifest 中 MAIN/LAUNCHER 一致）
		var APP_MAIN_ACTIVITY = "com.iknet.bloodmeasuredemo.MainActivity";

		// 应用商城后台登记的 appId（未预装走商城下载分支时使用，向运营确认）
		var APP_STORE_APP_ID = "479";

		// 应用商城 jumpId（沿用原模板，如有变更问运营）
		var APP_STORE_JUMP_ID = "8";

		// 应用商城包名（广东电信，一般不用改）
		var APP_STORE_PACKAGE = "com.amt.appstore.gddx";

		// ============================================================

		// 获取机顶盒型号
		function getSTBType(){
			var type = Authentication.CTCGetConfig("STBType");
			return type;
		}

		// 判断目标 APK 是否已安装在机顶盒上
		// 【修正】原版判断的是旧酷喵包 com.video.ytlook_SZDX，已改为 APP_PACKAGE
		function judgeApk(){
			return STBAppManager.isAppInstalled(APP_PACKAGE);
		}

		// 判断应用商城是否已安装（未安装则无法走下载分支）
		function judgeApp(){
			return STBAppManager.isAppInstalled(APP_STORE_PACKAGE);
		}

		// 获取用户退出 APK 后返回的 EPG 页面地址
		function getBackUrl(){
			var returnurl="<%=returnurl%>";
			var backUrl = null;
			if(returnurl!=""){
				backUrl=returnurl;
			} else {
				backUrl = Authentication.CTCGetConfig("EPGDomain");
			}
			return backUrl;
		}

		// 从 EPGDomain 配置中提取域名前缀（供商城和 APK 传参使用）
		function normalizeEPGDomain(rawDomain){
			var EPGDomain = rawDomain;
			if(EPGDomain.indexOf("smart")>0){
				EPGDomain = EPGDomain.split("smart")[0];
			} else if(EPGDomain.indexOf("CNEPG")>0){
				EPGDomain = EPGDomain.split("CNEPG")[0];
			} else {
				EPGDomain = EPGDomain.split("defaulthdcctv")[0];
			}
			return EPGDomain;
		}

		// 主入口：EPG 页面 onload 时自动执行
		function openApp(){
			// 大数据探针（沿用原模板）
			WkEpg.$('loading').style.opacity = 1;
			setTimeout(function() {
				createLogSdk();
			},300);

			var result = judgeApk();           // 目标 APK 是否已装
			var backUrl = getBackUrl();        // 返回地址
			var isAppInstall = judgeApp();     // 应用商城是否已装
			var userId = encryurID;            // 加密后的用户 ID（由 passwordEncryption.jsp 生成）
			var jsessionID = "<%=sessionId%>";
			var EPGDomain = normalizeEPGDomain(Authentication.CTCGetConfig("EPGDomain"));

			// 分支1：高清盒子不支持，跳转提示页
			if(fn_checkSTB()){
				window.location.href = EPGDomain + 'defaulthdcctv/gx2/page/guide/guide.jsp?returnurl=../index/index.jsp';

			// 分支2：未安装应用商城，无法下载 APK
			} else if (true != isAppInstall) {
				window.location.href = EPGDomain + 'defaulthdcctv/gx2/page/guide/guide2.jsp?returnurl=' + "<%=returnurl%>";

			// 分支3：商城已装，但目标 APK 未预装 → 打开应用商城下载
			} else if (true != result){
				var params = {
					appName: APP_STORE_PACKAGE,
					action: "com.amt.appstore.action.LAUNCHER",
					category: "android.intent.category.DEFAULT",
					extra: [
						{
							// extraKey 格式：jumpId + appPkg + appId，向应用商城运营确认
							name: "extraKey",
							value: "jumpId=" + APP_STORE_JUMP_ID + "&appPkg=" + APP_PACKAGE + "&appId=" + APP_STORE_APP_ID + "&account=null",
						},
						{ name: "sessionid", value: jsessionID },
						{ name: "domain", value: EPGDomain },
						{ name: "userid", value: userId },
						{ name: "backurl", value: backUrl }
					]
				};
				STBAppManager.startAppByIntent(JSON.stringify(params));
				window.location.href = backUrl;

			// 分支4：目标 APK 已预装 → 直接启动 MainActivity
			} else {
				var launchJson = {
					intentType: 0,
					appName: APP_PACKAGE,
					className: APP_MAIN_ACTIVITY,
					extra: [
						{ name: "userid", value: userId },
						{ name: "jsessionID", value: jsessionID },
						{ name: "epgDomain", value: EPGDomain },
						{ name: "spID", value: "szmg" }
					]
				};
				// 【修正】原版用手拼 JSON 字符串，容易因特殊字符出错，改用 JSON.stringify
				STBAppManager.startAppByIntent(JSON.stringify(launchJson));

				// 智慧家庭入口：退出 IPTV 应用；普通入口：返回 backUrl
				if(backUrl.indexOf("smarthomesmc") != -1 || backUrl.indexOf("smarthomesmg") != -1 || backUrl.indexOf("smarthomeszgx") != -1){
					Utility.setValueByName("exitIptvApp","***");
				} else {
					window.location.href = backUrl;
				}
			}
		}

	//------------------------------------大数据探针上报方法  Start------------------
	function pageLoad() {
		var p_mark = "health-apk";
		if (typeof(LogConfig) == "object" && LogConfig != null) {
			var pathName = XEpg.log(p_mark).getSimpleUrl(document.referrer);
			var referObj = getReferUrl(pathName);
			var tempObj = {};
			tempObj.p_type = "page";
			tempObj.page_id = "HEALTH_apk00000";
			tempObj.page_name = "家庭健康APK拉起页面";
			tempObj.refer_page_id = referObj.id;
			tempObj.refer_page_name = referObj.name;
			XEpg.log(p_mark).onload(tempObj);
		}
	}
	//------------------------------------大数据探针上报方法  End------------------
	</script>
  </head>
  <body onload="openApp()">
    <div id="loading" style="opacity:0;font-size:40px;color:white;position:fixed;left:90%;top:90%;margin:-20px -120px">加载中...</div>
  </body>
</html>
