package com.iknet.iknetbluetoothlibrary.config;

import android.content.Context;
import android.content.SharedPreferences;
import android.content.SharedPreferences.Editor;

/**
 * android SharedPreference 轻量级缓存
 * 
 * @author www.1knet.com
 * 
 */

public class ShareConfig{
	private static ShareConfig instance;
	private Context mContext;
	private SharedPreferences mPreferences;

	public static ShareConfig getInstance(Context context) {
		if (instance == null) {
			instance = new ShareConfig(context);
		}
		return instance;
	}

	public ShareConfig(Context context) {
		mContext = context;
		if (context != null) {
			mPreferences = context.getSharedPreferences(
					"SAVE_USER_INFO", 1);
		}
		setShareConfig(this);
	}

	private void setShareConfig(ShareConfig shareConfig) {
		instance = shareConfig;
	}

//	public void saveObject(Object obj, String text) {
//		String oAuth_Base64 = ObjectToBase64(obj);
//		Editor editor = mPreferences.edit();
//		editor.putString(text, oAuth_Base64);
//		editor.commit();
//	}
//
//	public Object read(String text) {
//		Object obj = null;
//		String productBase64 = mPreferences.getString(text, "");
//		// 读取字节
//		byte[] base64 = Base64.decodeBase64(productBase64.getBytes());
//		// 封装到字节流
//		ByteArrayInputStream bais = new ByteArrayInputStream(base64);
//		try {
//			// 再次封装
//			ObjectInputStream bis = null;
//			try {
//				bis = new ObjectInputStream(bais);
//				// 读取对象
//				obj = bis.readObject();
//			} catch (ClassNotFoundException e) {
//				e.printStackTrace();
//			}
//		} catch (StreamCorruptedException e) {
//			e.printStackTrace();
//		} catch (IOException e) {
//			e.printStackTrace();
//		}
//		return obj;
//	}

	public void putPreferencesVal(String key, String value) {
		SharedPreferences.Editor editor = mPreferences.edit();
		editor.putString(key, value);
		editor.commit();
	}

	public String getPreferencesVal(String key, String defaultVal) {
		return mPreferences.getString(key, defaultVal);
	}

	public void remove(String key) {
		SharedPreferences preferences = mContext.getSharedPreferences(
				"SAVE_USER_INFO", 1);
		Editor ed = preferences.edit();
		ed.remove(key);
		ed.commit();
	}

	public void clear() {
		SharedPreferences preferences = mContext.getSharedPreferences(
				"SAVE_USER_INFO", 1);
		Editor ed = preferences.edit();
		ed.remove("result");
		ed.remove("deviceName");
		ed.commit();
	}
	
}
