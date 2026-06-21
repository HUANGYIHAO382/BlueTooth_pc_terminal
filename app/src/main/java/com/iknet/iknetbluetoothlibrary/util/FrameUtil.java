package com.iknet.iknetbluetoothlibrary.util;

import java.util.ArrayList;
import java.util.Arrays;

import android.annotation.SuppressLint;
import android.app.ActivityManager;
import android.app.ActivityManager.RunningServiceInfo;
import android.content.Context;
import android.util.Log;

/**
 * 
 * @author lanxiangru
 * 
 */
public class FrameUtil {

	public static final int BYTE_MAX_VALUE = 256;

	// 帧头
	public static final byte[] HEAD_PRE_SEND = {(byte)0x34};
	public static final byte[] HEAD_PRE_SEND_NUMS = {(byte)0x55};
	
	public static final byte[] HEAD_PRE_RESPONSE = {(byte)0x32};
	public static final byte[] HEAD_PRE_RESPONSE_TIME = {(byte)0x66};
	public static final byte[] HEAD_PRE_RESPONSE_ALARM = {(byte)0x77};
	
	
	// 帧尾
	public static final String END_PRE_SEND = "00FF";
	public static final String END_PRE_RESPONSE = "00FF";

	/**
	 * 获得帧长度 帧头 功能码 长度 数据域 校验 结束
	 * 
	 * @param dataLen
	 *            数据域长度
	 * @return
	 */
	protected static int getFrameLength(int dataLen) {
		return 2 + 2 + 1 + dataLen + 1 + 2;
	}

	/**
	 * 获得检验位, 从帧头到校验位前所有字节的累加和，不超过256的溢出值。
	 * 
	 * @param optCode
	 * @param length
	 * @param data
	 * @return
	 */
	private static byte checkStyle(byte[] bytes, int toIndex) {
		byte count = 0;
		for (int i = 0; i < toIndex; i++) {
			count += bytes[i];
		}
		return count;
	}

	

	/**
	 * 十六进制字符串转字节码
	 * 
	 * @param b
	 * @return
	 */
	public static byte[] hex2byte(byte[] b) {
		if ((b.length % 2) != 0) {
			System.out.println("ERROR: 转化失败  le= " + b.length + " b:" + b.toString());
			return null;
		}
		byte[] b2 = new byte[b.length / 2];
		for (int n = 0; n < b.length; n += 2) {
			// if(n+2<=b.length){
			String item = new String(b, n, 2);
			// 两位一组，表示一个字节,把这样表示的16进制字符串，还原成一个进制字节
			b2[n / 2] = (byte) Integer.parseInt(item, 16);
			// }else{
			// String item = new String(b, n, 1);
			// // 两位一组，表示一个字节,把这样表示的16进制字符串，还原成一个进制字节
			// b2[n / 2] = (byte) Integer.parseInt(item, 16);
			// }

		}
		b = null;
		return b2;
	}

	/**
	 * int 型转换成字节数组
	 * 
	 * @param i
	 * @return
	 */
	public static byte[] int2Bytes(int i) {
		if (i < 256) {// 1个字节
			return new byte[] { (byte) i };
		} else {
			Log.e("Integer.toHexString(i)===", Integer.toHexString(i));
			Log.e("Integer.toHexString(i).getBytes()++++++", Integer
					.toHexString(i).getBytes() + "");

			String a;

			byte[] b = Integer.toHexString(i).getBytes();
			if ((b.length % 2) != 0) {
				a = "0" + Integer.toHexString(i);
			} else {
				a = Integer.toHexString(i);
			}

			return hex2byte(a.getBytes());
		}
	}

	/**
	 * int 型转换成字节数组
	 * 
	 * @param i
	 * @param emptyBitCount
	 *            空位数
	 * @return
	 */
	public static byte[] int2Bytes(int i, int emptyBitCount) {
		String hex = "";
		for (int k = 0; k < emptyBitCount; k++) {
			hex += (i < 16 ? "000" : "00");
		}

		hex = hex + Integer.toHexString(i);
		return hex2byte(hex.getBytes());

		// return DataPacketUtils.int2ByteArray(i, emptyBitCount+1);
	}

	/**
	 * 0~65536的数转化成2字节
	 * 
	 * @return
	 */
	public static byte[] intTo2Bytes(int i) {
		
		return int2ByteArray(i,2);
//		if (i > FrameUtil.BYTE_MAX_VALUE) {
//			return FrameUtil.int2Bytes(i);
//			// return DataPacketUtils.int2ByteArray(i,2);
//		} else {
//			return FrameUtil.int2Bytes(i, 1);
//			// return DataPacketUtils.int2ByteArray(i,1);
//		}
	}
	
	/**
	 * int转byte数组�?存储顺序为从0-3byte, 0存最低字节（小头存储�?
	 * @param intValue �?��转化的int�?
	 * @param arrayLegth  输出的byte数组长度，最大为4（int占用4个字节）
	 */
	public static byte[] int2ByteArray(int intValue, int arrayLegth) {
		byte[] bLocalArr = new byte[arrayLegth];
		int len = arrayLegth<4 ? arrayLegth : 4; //�?��的长�?
		
		for (int i = 0; i < len; i++) {
			bLocalArr[len-1-i] = (byte) (intValue >> 8 * i & 0xFF);
		}
		return bLocalArr;
	}

	public static byte int2Byte(int i) {
		return (byte) i;
	}

	/**
	 * 字节码转int型
	 * 
	 * @param b
	 * @return
	 */
	public static int bytes2Int(byte[] b) { // 一个字节的数，
		return Integer.valueOf(byte2hex(b), 16);
	}

	/**
	 * 字节码转十六进制字符串
	 * 
	 * @param b
	 * @return
	 */
	public static String byte2hex(byte[] b) { // 一个字节的数，

		// 转成16进制字符串
		String hs = "";
		String tmp = "";
		for (int n = 0; n < b.length; n++) {
			// 整数转成十六进制表示

			tmp = (java.lang.Integer.toHexString(byteToInt(b[n])));
			if (tmp.length() == 1) {
				hs = hs + "0" + tmp;
			} else {
				hs = hs + tmp;
			}
		}
		tmp = null;
		return hs.toUpperCase(); // 转成大写
	}

	// /**
	// * int到byte[]
	// *
	// * @param i
	// * @return
	// */
	// public static byte[] intToByteArray(int i) {
	// byte[] result = new byte[4];
	// // 由高位到低位
	// result[0] = (byte) ((i >> 24) & 0xFF);
	// result[1] = (byte) ((i >> 16) & 0xFF);
	// result[2] = (byte) ((i >> 8) & 0xFF);
	// result[3] = (byte) (i & 0xFF);
	// return result;
	// }
	//
	// /**
	// * byte[]转int
	// *
	// * @param bytes
	// * @return
	// */
	// public static int byteArrayToInt(byte[] bytes) {
	// int value = 0;
	// // 由高位到低位
	// for (int i = 0; i < bytes.length; i++) {
	// int shift = (4 - 1 - i) * 8;
	// value += (bytes[i] & 0x000000FF) << shift;// 往高位游
	// }
	// return value;
	// }

	/**
	 * byte转int
	 * 
	 * @param b
	 * @return
	 */
	public static int byteToInt(byte b) {
		return b & 0XFF;
	}

	/**
	 * 拼接数组
	 * 
	 * @param <T>
	 * @param first
	 * @param second
	 * @return
	 */
	@SuppressLint("NewApi")
	public static byte[] concat(byte[] first, byte[]... others) {
		if (others.length == 1 && others[0] == null) {
			return first;
		}
		switch (others.length) {
		case 0:
			return first;
		case 1: {
			byte[] result = Arrays.copyOf(first, first.length
					+ others[0].length);
			System.arraycopy(others[0], 0, result, first.length,
					others[0].length);
			return result;
		}
		default: {
			return concat(concat(first, others[0]),
					Arrays.copyOfRange(others, 1, others.length));
		}
		}
	}

	/**
	 * int型数组转化成字节组
	 * 
	 * @return
	 */
	public static byte[] integers2Bytes(ArrayList<Integer> addrList) {
		byte[] bytes = new byte[2 * addrList.size()];
		for (int i = 0; i < addrList.size(); i++) {
			byte[] bs = FrameUtil.intTo2Bytes(addrList.get(i));
			// if(bs.length==2){
			bytes[2 * i] = bs[0];
			bytes[2 * i + 1] = bs[1];
			// }else{
			// bytes[2 * i] = 0;
			// bytes[2 * i + 1] = bs[0];
			// }
		}
		return bytes;
	}

	/**
	 * 数组内字节异或
	 * 
	 * @param bytes
	 * @return
	 */
	public static byte xor(byte[] bytes) {
		if (bytes == null || bytes.length == 0) {
			return (byte) 0;
		} else {
			int b = bytes[0];
			for (int i = 1; i < bytes.length; i++) {
				b ^= bytes[i];
			}
			return (byte) b;
		}
	}

	public static boolean compareTo(byte[] source, byte[] dest) {
		int length1 = source.length;
		int length2 = dest.length;

		if (length1 != length2) // 数组长度不一致
			return false;

		for (int i = 0; i < length1; i++) {
			if (source[i] != dest[i])
				return false;
		}

		return true;
	}
	
	/**
	 * Unicode转汉字
	 * @param data
	 * @author 太平洋的风
	 * @return
	 */
	public static String decodeUnicode(byte[] data){
		StringBuffer sb = new StringBuffer();
		char c;
		byte b1 = 0,b2;
		for(int j=0; j<data.length; j++){
			if(j%2 == 0){
				b1 = data[j];
			}else if(j%2 == 1){
				b2 = data[j];
				c = (char) (((b2 & 0xFF) << 8) | (b1 & 0xFF));
				sb.append(c);
			}
		}
		
		return sb.toString().trim();
	}
	
	/**
	 * 判断服务是否在运行
	 * @return
	 */
	public static boolean isServiceRunning(String serviceClassName, Context context) {
	    ActivityManager manager = (ActivityManager) context.getSystemService(Context.ACTIVITY_SERVICE);
	    for (RunningServiceInfo service : manager.getRunningServices(Integer.MAX_VALUE)) {
	        if (serviceClassName.equals(service.service.getClassName())) {
	            return true;
	        }
	    }
	    return false;
	}
}
