package com.iknet.iknetbluetoothlibrary.util;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.provider.Settings;
import android.util.Log;

import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

public class PermissionUtil {
	private static String TAG = "PermissionUtil";
	
	public static final int REQUEST_CODE_PERMISSION_SETTING = 102;
	
	// 启动应用的设置
    public static void startAppSettings(Context context) {
        Intent intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS);
        intent.setData(Uri.parse("package:" + context.getPackageName()));
        ((Activity) context).startActivityForResult(intent, REQUEST_CODE_PERMISSION_SETTING);
    }
	
	public static final int REQUEST_FINE_LOCATION = 101;
	/** 23以上版本蓝牙扫描需要定位权限 
	 * 
	 * */
	public static void requestLocationPerm(Context context) {
		if (!checkLocationPermission(context)) {
			// 判断是否需要 向用户解释，为什么要申请该权限
			if (ActivityCompat.shouldShowRequestPermissionRationale((Activity)context, Manifest.permission.ACCESS_COARSE_LOCATION)){
			}
			Log.v(TAG, "请求定位权限");
			ActivityCompat.requestPermissions((Activity)context, new String[] { Manifest.permission.ACCESS_COARSE_LOCATION }, REQUEST_FINE_LOCATION);
		}
	}
	
	/**
	 * 是否获取到了定位权限
	 * @return
	 */
	public static boolean checkLocationPermission(Context context){
		int checkPermission = ContextCompat.checkSelfPermission(
				context, Manifest.permission.ACCESS_COARSE_LOCATION);
		return checkPermission == PackageManager.PERMISSION_GRANTED;
	}
	

}
