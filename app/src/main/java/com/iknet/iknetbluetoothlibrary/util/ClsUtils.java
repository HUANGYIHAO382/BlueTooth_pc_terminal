package com.iknet.iknetbluetoothlibrary.util;

import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.util.Log;

/**
 * 手动进行蓝牙配对
 * @author 1knet.com
 *
 */
public class ClsUtils {
	private static final String TAG = "ClsUtils";
	
	private static BluetoothDevice remoteDevice;

	public ClsUtils() {
		// TODO Auto-generated constructor stub
	}

	/**
	 * 与设备配对 参考源码
	 */
	static public boolean createBond(Class<? extends BluetoothDevice> btClass,
			BluetoothDevice btDevice) throws Exception {

		Method createBondMethod = btClass.getMethod("createBond");
		Boolean returnValue = (Boolean) createBondMethod.invoke(btDevice);
		Log.v(TAG, "创建配对:" + returnValue.booleanValue());
		return returnValue.booleanValue();
	}

	/**
	 * 与设备解除配对 参考源码
	 */
	static public boolean removeBond(Class<? extends BluetoothDevice> btClass,
			BluetoothDevice btDevice) throws Exception {
		Method removeBondMethod = btClass.getMethod("removeBond");
		Boolean returnValue = (Boolean) removeBondMethod.invoke(btDevice);
		return returnValue.booleanValue();
	}

	static public boolean setPin(Class<? extends BluetoothDevice> btClass, BluetoothDevice btDevice,
			String str) throws Exception {
		try {
			Method removeBondMethod = btClass.getDeclaredMethod("setPin",
					new Class[] { byte[].class });
			Boolean returnValue = (Boolean) removeBondMethod.invoke(btDevice,
					new Object[] { str.getBytes() });
			Log.v(TAG, "设置pin码:" + returnValue.booleanValue());
			return returnValue.booleanValue();
		} catch (SecurityException e) {
			// throw new RuntimeException(e.getMessage());
			e.printStackTrace();
		} catch (IllegalArgumentException e) {
			// throw new RuntimeException(e.getMessage());
			e.printStackTrace();
		} catch (Exception e) {
			// TODO Auto-generated catch block
			e.printStackTrace();
		}
		return false;

	}

	// 取消用户输入
	static public boolean cancelPairingUserInput(Class<?> btClass, BluetoothDevice device)
					throws Exception {
		Method createBondMethod = btClass.getMethod("cancelPairingUserInput");
		boolean cancelBondProcess = cancelBondProcess(btClass, device);
		Boolean returnValue = (Boolean) createBondMethod.invoke(device);
		Log.v(TAG, "取消对话框cancelPairingUserInput:" + returnValue.booleanValue() + "，取消配对线程：" + cancelBondProcess);
		return returnValue.booleanValue();
	}

	// 取消配对线程
	static public boolean cancelBondProcess(Class<?> btClass, BluetoothDevice device)
					throws Exception {
		Method createBondMethod = btClass.getMethod("cancelBondProcess");
		Boolean returnValue = (Boolean) createBondMethod.invoke(device);
		return returnValue.booleanValue();
	}

	/**
	 * 
	 * @param clsShow
	 */
	static public void printAllInform(Class<?> clsShow) {
		try {
			// 取得所有方法
			Method[] hideMethod = clsShow.getMethods();
			int i = 0;
			for (; i < hideMethod.length; i++) {
				Log.e("method name", hideMethod[i].getName() + ";and the i is:"
						+ i);
			}
			// 取得所有常量
			Field[] allFields = clsShow.getFields();
			for (i = 0; i < allFields.length; i++) {
				Log.e("Field name", allFields[i].getName());
			}
		} catch (SecurityException e) {
			// throw new RuntimeException(e.getMessage());
			e.printStackTrace();
		} catch (IllegalArgumentException e) {
			// throw new RuntimeException(e.getMessage());
			e.printStackTrace();
		} catch (Exception e) {
			// TODO Auto-generated catch block
			e.printStackTrace();
		}
	}
	
	/** 流程有问题 */
	static private boolean pair(BluetoothDevice device, String strPsw) {
		boolean result = false;

		if (device.getBondState() != BluetoothDevice.BOND_BONDED) {
			try {
				Log.d(TAG, "NOT BOND_BONDED");
				// 手机和蓝牙采集器配对
				if(setPin(device.getClass(), device, strPsw)){
					result = createBond(device.getClass(), device);
					result = cancelPairingUserInput(device.getClass(), device);
				}else{
					result = false;
				}
				
			} catch (InvocationTargetException e) {
				result = false;
				Log.d(TAG, "setPiN failed!");
				e.printStackTrace();
			} catch (Exception e) {
				result = false;
				Log.d(TAG, "setPiN failed!");
				e.printStackTrace();
			}

		} else {
			Log.d(TAG, "HAS BOND_BONDED");
			result = true;
		}
		Log.v(TAG, "配对结果：" + result);
		
		return result;
	}

	static public boolean pair(String strAddr, String strPsw) {
		boolean result = false;
		BluetoothAdapter bluetoothAdapter = BluetoothAdapter
				.getDefaultAdapter();

		bluetoothAdapter.cancelDiscovery();

		if (!bluetoothAdapter.isEnabled()) {
			bluetoothAdapter.enable();
		}

		BluetoothDevice device = bluetoothAdapter.getRemoteDevice(strAddr);

		if (device.getBondState() != BluetoothDevice.BOND_BONDED) {
			try {
				Log.d(TAG, "NOT BOND_BONDED");
				ClsUtils.setPin(device.getClass(), device, strPsw); // 手机和蓝牙采集器配对
				ClsUtils.createBond(device.getClass(), device);
				cancelPairingUserInput(device.getClass(), device);
				remoteDevice = device; // 配对完毕就把这个设备对象传给全局的remoteDevice

				result = true;

			} catch (Exception e) {
				// TODO Auto-generated catch block
				Log.d(TAG, "setPiN failed!");
				e.printStackTrace();
			}

		} else {
			Log.d(TAG, "HAS BOND_BONDED");
//			try {
//				ClsUtils.removeBond(device.getClass(), device);
//				// ClsUtils.createBond(device.getClass(), device);
//				boolean flag1 = ClsUtils.setPin(device.getClass(), device,
//						strPsw); // 手机和蓝牙采集器配对
//				boolean flag2 = ClsUtils.createBond(device.getClass(), device);
//				cancelPairingUserInput(device.getClass(), device);
//				// remoteDevice = device; // 如果绑定成功，就直接把这个设备对象传给全局的remoteDevice
//
//				result = true;
//
//			} catch (Exception e) {
//				// TODO Auto-generated catch block
//				Log.d(TAG, "setPiN failed!");
//				e.printStackTrace();
//			}
			result = true;
		}
		Log.v(TAG, "配对结果：" + result);
		return result;
	}

}