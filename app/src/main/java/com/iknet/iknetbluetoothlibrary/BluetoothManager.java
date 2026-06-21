package com.iknet.iknetbluetoothlibrary;


import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

import com.iknet.bloodmeasuredemo.R;
import com.iknet.iknetbluetoothlibrary.util.FrameUtil;
import com.iknet.iknetbluetoothlibrary.util.PermissionUtil;

import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.ContextWrapper;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.text.TextUtils;
import android.util.Log;
import android.widget.Toast;

/**
 * 蓝牙管理器
 * @author 1knet.com
 *
 */
public class BluetoothManager extends ContextWrapper{
	private static final String TAG = "BluetoothManager";
	
	private static BluetoothManager instance;
	private boolean isRegistBroadcast = false;

	private BluetoothAdapter _bluetooth = BluetoothAdapter.getDefaultAdapter();
	private static Context mContext;
	private List<BluetoothDevice> deviceList = new ArrayList<BluetoothDevice>();
	
	private MyReceiver myReceiver;
	private OnBTMeasureListener mOnBTMeasureListener;
	
	private int onDiscoveryFinishedCount = 0;
	
	public static final int MIN_POWER = 3600;

	private static MeasureState measureState = MeasureState.DEFAULT; // 测量状态

	public enum MeasureState {
		DEFAULT, OPENING, OPENED, RESEARCHING, CONNECTING, CONNECTED, MEASURING
	}

	public static BluetoothManager getInstance(Context context) {
		if (instance == null) {
			instance = new BluetoothManager(context);
		}else if(mContext != null && !mContext.toString().equals(context.toString())){
			instance = new BluetoothManager(context);
		}
		return instance;
	}
	
	private BluetoothManager(Context context){
		super(context);
		mContext = context;
	}
	
	/**
	 * 初始化sdk
	 */
	public void initSDK(){
		initReceiver();
	}
	
	/**
	 * 开始蓝牙事务
	 */
	public void startBTAffair(OnBTMeasureListener onBTMeasureListener){
		initReceiver();
		if(_bluetooth == null){
			Toast.makeText(mContext, "未检测到蓝牙设备", Toast.LENGTH_SHORT).show();
			return;
		}
		if(!_bluetooth.enable()){
			Toast.makeText(mContext, "请打开蓝牙", Toast.LENGTH_SHORT).show();
			return;
		}
		Log.v(TAG, "启动蓝牙事务");
		mOnBTMeasureListener = onBTMeasureListener;
		
		if(!TextUtils.isEmpty(BluetoothService.ConnectedBTAddress)){
			mOnBTMeasureListener.onConnected(true, _bluetooth.getRemoteDevice(BluetoothService.ConnectedBTAddress));
			startMeasure();
		} else {
			setBtDiscoverable();
			searchBluetooth();
		}
		
	}
	
	/**
	 * 关闭蓝牙事务并断开蓝牙连接
	 */
	public void stopBTAffair() {
		if (isRegistBroadcast) {
			mContext.unregisterReceiver(myReceiver);
			isRegistBroadcast = false;
		}
		if(_bluetooth.isDiscovering()){
			_bluetooth.cancelDiscovery();
		}
		// stopMeasure();
		// sendBroadcast(new Intent(BluetoothService.ACTION_BT_DISCONNECT_TO));
	}
	
	/**
	 * 通过反射调用setScanMode，设置蓝牙可见性
	 */
	private void setBtDiscoverable(){
		try {
			Class<?> ba = _bluetooth.getClass();
			Method m = ba.getMethod("setScanMode", new Class<?>[]{int.class});
			boolean b = (Boolean) m.invoke(_bluetooth, BluetoothAdapter.SCAN_MODE_CONNECTABLE_DISCOVERABLE);
			Log.v(TAG, "setBtDiscoverable-设置蓝牙可见性：" + b);
		} catch (Exception e) {
			e.printStackTrace();
			Log.v(TAG, "setBtDiscoverable-设置蓝牙可见性错误");
		}
	}

	/**
	 * 启动测量
	 */
	public boolean startMeasure(){
		if(TextUtils.isEmpty(BluetoothService.ConnectedBTAddress)){
//			Toast.makeText(mContext, "未连接蓝牙设备！", Toast.LENGTH_SHORT).show();
			return false;
		}
		
		//查询电量后如果>3600才进行测量操作，设备返回电量后发送启动指令
		sendData("cc80020304040001");
		Log.v(TAG, "发送查询电量指令：" + "cc80020304040001");
		
		return true;
	}
	
	/**
	 * 停止测量
	 */
	public void stopMeasure(){
		if(TextUtils.isEmpty(BluetoothService.ConnectedBTAddress)){
			Toast.makeText(mContext, getString(R.string.not_connect_bluetooth), Toast.LENGTH_SHORT).show();
			return;
		}
		sendData("cc80020301030003");
		Log.v(TAG, "发送停止测量指令：" + "cc80020301030003");
	}
	
	/**
	 * 是否为连接蓝牙设备状态
	 * @return
	 */
	public boolean isConnectBT(){
		if(TextUtils.isEmpty(BluetoothService.ConnectedBTAddress)){
			return false;
		}else{
			return true;
		}
	}
	
	/**
	 * 关闭手机蓝牙并且注销广播
	 */
	public void closeBT(){
		new Handler().postDelayed(new Runnable() {
			@Override
			public void run() {
				if (isRegistBroadcast) {
					mContext.unregisterReceiver(myReceiver);
					isRegistBroadcast = false;
				}
				if (_bluetooth.isEnabled()) {
					_bluetooth.disable();
				}
			}
		}, 100);
	}
	
	/**
	 * 发送数据给蓝牙设备，比如"cc80020301030003"
	 * @param dataStr
	 */
	private void sendData(String dataStr) {
		byte[] data = hex2byte(dataStr.getBytes());
		Intent intent = new Intent(BluetoothService.ACTION_BLUETOOTH_DATA_WRITE);
		intent.putExtra(BluetoothService.ACTION_BLUETOOTH_DATA_EXTRA_BYTEARRAY, data);
		sendBroadcast(intent);
	}
	
	private void initReceiver() {
		if (!isRegistBroadcast) {
			Log.d(TAG, "initReceiver");
			myReceiver = new MyReceiver();
			IntentFilter filter = new IntentFilter(BluetoothService.ACTION_BLUETOOTH_CONNECT);
			filter.addAction(BluetoothService.ACTION_BLUETOOTH_CONNECT2);
			filter.addAction(BluetoothService.ACTION_BLUETOOTH_DATA_READ);
			filter.addAction(BluetoothService.ACTION_BLUETOOTH_RUNNING);
			filter.addAction(BluetoothService.ACTION_BLUETOOTH_POWER);
			filter.addAction(BluetoothService.ACTION_ERROR_MEASURE);
			filter.addAction(BluetoothDevice.ACTION_FOUND);
			filter.addAction(BluetoothAdapter.ACTION_DISCOVERY_FINISHED);
			filter.addAction(BluetoothDevice.ACTION_ACL_DISCONNECTED);
			filter.addAction(BluetoothAdapter.ACTION_STATE_CHANGED);
			mContext.registerReceiver(myReceiver, filter);
			isRegistBroadcast = true;
		}
	}

	// 监听蓝牙的连接状态
	private class MyReceiver extends BroadcastReceiver {
		@Override
		public void onReceive(Context context, Intent intent) {
			String action = intent.getAction();
			Log.d(TAG, "MyReceiver-action:" + action);
			if (BluetoothService.ACTION_BLUETOOTH_CONNECT.equals(action)) {
				// 第一次握手是否成功
				boolean connect = intent.getBooleanExtra(BluetoothService.ACTION_BLUETOOTH_CONNECT_EXTRA_BOOLEAN,
						false);

				if (connect) {
					if(BluetoothService.connectedDeviceType == BluetoothService.DeviceType.TYPE_88A){
						Log.v(TAG, "发送连接血压计指令：" + "cc80020301010001");
						sendData("cc80020301010001");// cccc020301010001连接蓝牙，第二次握手执行
					}else if(BluetoothService.connectedDeviceType == BluetoothService.DeviceType.TYPE_9000){
						//9000类型设备不需要进行第二次握手
						if (deviceList.size() > 0) {
							mOnBTMeasureListener.onConnected(connect, deviceList.get(0));
						}
					}
				} else {
					if (deviceList.size() > 0) {
						mOnBTMeasureListener.onConnected(connect, deviceList.get(0));
					}
				}
				
			} else if(BluetoothService.ACTION_BLUETOOTH_CONNECT2.equals(action)){
				//第二次握手是否成功
				boolean connect = intent.getBooleanExtra(BluetoothService.ACTION_BLUETOOTH_CONNECT_EXTRA_BOOLEAN,false);
				mOnBTMeasureListener.onConnected(connect, deviceList.get(0));
				if(connect){
					sendData("cc80020304040001");
					Log.v(TAG, "发送查询电量指令：" + "cc80020304040001");
				}
			} else if (BluetoothService.ACTION_ERROR_MEASURE.equals(action)) {
				//测量失败
				Log.v(TAG, "测量失败");
//				sendData("cc80020301030003");
//				Log.v(TAG, "发送停止测量指令：" + "cc80020301030003");
//				new Thread(new Runnable() {
//					@Override
//					public void run() {
//						try {
//							Looper.prepare();
//							Thread.sleep(8000);
//							sendData("cc80020301040004");
//							Log.v(TAG, "发送关机指令：" + "cc80020301040004");
//							mOnBTMeasureListener.onMeasureError();
//						} catch (InterruptedException e) {
//							e.printStackTrace();
//						}
//					}
//				}).start();
				new Handler().postDelayed(new Runnable() {
					@Override
					public void run() {
						sendData("cc80020301040004");
						Log.v(TAG, "发送关机指令：" + "cc80020301040004");
						mOnBTMeasureListener.onMeasureError();
					}
				}, 8000);
			} else if (BluetoothService.ACTION_BLUETOOTH_POWER.equals(action)) {
				// 设置设备的电量的变化
				String power = intent.getStringExtra("power");
				mOnBTMeasureListener.onPower(power);
				if(Integer.parseInt(power) > MIN_POWER){
					sendData("cc80020301020002");
					Log.v(TAG, "发送启动测量指令：" + "cc80020301020002");
					setMeasureState(MeasureState.MEASURING);
				}
			} else if (BluetoothService.ACTION_BLUETOOTH_RUNNING.equals(action)) {
				// 正在测量，数据在发生变化，时刻更新数据显示
				String running = intent.getStringExtra("running");
				mOnBTMeasureListener.onRunning(running);
			} else if (BluetoothService.ACTION_BLUETOOTH_DATA_READ.equals(action)) {
				// 测量结束，结果显示
				postDataReadAction(context, intent);
			}else if (BluetoothDevice.ACTION_FOUND.equals(action)) {
				BluetoothDevice device = intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE);
				String str = device.getName() + "-" + device.getAddress();
				Log.v(TAG, "搜索到的设备：" + str);
				String arg = str.substring(0, 3);
				if (check(device.getAddress())) {
					if (arg.equals("RBP") || arg.contains("BP")) {
						deviceList.add(device);
						if (_bluetooth.isDiscovering()) {
							_bluetooth.cancelDiscovery();
						}
					}
				}
			} else if (BluetoothAdapter.ACTION_DISCOVERY_FINISHED.equals(action)) {
//				startBtService();
				++onDiscoveryFinishedCount;
				if(onDiscoveryFinishedCount == 1){
					Log.v(TAG, "搜索完成-搜索到设备数量：" + deviceList.size());
					mOnBTMeasureListener.onFoundFinish(deviceList);
					if(deviceList.size() > 0){
						connectToBT(deviceList.get(0).getAddress());
					}
				}
			} else if (action.equals(BluetoothDevice.ACTION_ACL_DISCONNECTED)) {
				//断开连接
				BluetoothDevice device = intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE);
				if(device != null){
					mOnBTMeasureListener.onDisconnected(device);
				}

				deviceList.clear();
			} else if (action.equals(BluetoothAdapter.ACTION_STATE_CHANGED)) {
				int state = intent.getIntExtra(BluetoothAdapter.EXTRA_STATE, BluetoothAdapter.ERROR);
				switch (state) {
				case BluetoothAdapter.STATE_OFF:
					setMeasureState(MeasureState.DEFAULT);
					break;
				case BluetoothAdapter.STATE_TURNING_OFF:
					break;
				case BluetoothAdapter.STATE_ON:
					setMeasureState(MeasureState.OPENED);
					break;
				case BluetoothAdapter.STATE_TURNING_ON:
					setMeasureState(MeasureState.OPENING);
					break;
				}
			} else if (action.equals(BluetoothAdapter.ACTION_DISCOVERY_STARTED)) {
				setMeasureState(MeasureState.RESEARCHING);
			} else if (action.equals(BluetoothAdapter.ACTION_CONNECTION_STATE_CHANGED)) {
				int state = intent.getIntExtra(BluetoothAdapter.EXTRA_CONNECTION_STATE, BluetoothAdapter.ERROR);
				switch (state) {
				case BluetoothAdapter.STATE_CONNECTING:
					setMeasureState(MeasureState.CONNECTING);
					break;
				case BluetoothAdapter.STATE_CONNECTED:
					// 连接成功后要进行验证才能开始测量
					setMeasureState(MeasureState.CONNECTED);
					break;
				default:
					break;
				}
			}
		}

	}
	
	/** 连接蓝牙设备 */
	private void connectToBT(String addr){
		Log.v(TAG, "开始连接蓝牙：" + addr);
		if(FrameUtil.isServiceRunning("com.iknet.iknetbluetoothlibrary.BluetoothService", mContext)){
			Intent intent = new Intent(BluetoothService.ACTION_BT_CONNECT_TO);
			intent.putExtra("addr", addr);
			mContext.sendBroadcast(intent);
		}else{
			//启动Service，连接蓝牙设备
			Intent intent2 = new Intent(mContext.getApplicationContext(),BluetoothService.class);
			intent2.putExtra("PREFS_BLUETOOTH_PRE_ADDR_STRING", addr);
			mContext.startService(intent2);
		}
		
	}
	
	private void postDataReadAction(Context context, Intent intent) {
		Bundle bundle = intent.getExtras();
		MeasurementResult result = (MeasurementResult) bundle.getSerializable("result");
		sendData("cc80020301030003");// 测量完后发送停止命令
		Log.v(TAG, "发送停止测量指令：" + "cc80020301030003");
		mOnBTMeasureListener.onMeasureResult(result);
	}
	
	/**
	 * 搜索蓝牙设备
	 */
	public void searchBluetooth() {
		if(Build.VERSION.SDK_INT >= 23){
			requestLocationPerm();
		}else{
			doDiscovery();
		}
	}
	
	public static final int REQUEST_FINE_LOCATION = PermissionUtil.REQUEST_FINE_LOCATION;
	/** 23以上版本蓝牙扫描需要定位权限 */
	private void requestLocationPerm() {
		if (!PermissionUtil.checkLocationPermission(this)) {
			PermissionUtil.requestLocationPerm(mContext);
			
		} else {
			doDiscovery();
		}
	}
	
	/**
	 * 搜索设备
	 */
	private void doDiscovery() {
		onDiscoveryFinishedCount = 0;
		deviceList.clear();
		if(!_bluetooth.isEnabled()){
			Toast.makeText(this,"请打开蓝牙",Toast.LENGTH_SHORT).show();
			return;
		}
		if (_bluetooth.isDiscovering()) {
			_bluetooth.cancelDiscovery();
		}
		Log.v(TAG, "开始搜索");
		_bluetooth.startDiscovery();
	}
	
	/** 扫描le蓝牙设备 */
	/*@SuppressLint("NewApi")
	private void scanLeDevice(boolean enable){
		if(enable){
			_bluetooth.startLeScan(leScanCallback);
		}else{
			_bluetooth.stopLeScan(leScanCallback);
		}
	}
	
	@SuppressLint("NewApi")
	private LeScanCallback leScanCallback = new BluetoothAdapter.LeScanCallback() {
		
		@Override
		public void onLeScan(BluetoothDevice device, int rssi, byte[] scanRecord) {
			String str = device.getName() + "\n" + device.getAddress();
			Log.v(TAG, "搜索到的ble设备：" + str);
			String arg = str.substring(0, 3);
			if (check(device.getAddress())) {
				if (arg.equals("RBP")) {
					deviceList.add(device);
					_bluetooth.stopLeScan(leScanCallback);
					startBtService();
				}
			}
		}
	};*/
	
	// 检查列表中的蓝牙地址中是否存在该地址，避免重复添加
	private boolean check(String address) {
		int count = deviceList.size();
		for (int i = 0; i < count; i++) {
			if (deviceList.get(i).getAddress().equals(address))
				return false;
		}
		return true;
	}
	
	/**
	 * 十六进制字符串转字节码
	 * 
	 * @param b
	 * @return
	 */
	private static byte[] hex2byte(byte[] b) {
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
		}
		b = null;
		return b2;
	}

	public static MeasureState getMeasureState() {
		return measureState;
	}

	/**
	 * 标记测量过程时的状态
	 * 
	 * @param measureState
	 */
	public static void setMeasureState(MeasureState measureState) {
		BluetoothManager.measureState = measureState;
	}

	public interface OnBTMeasureListener {
		/**
		 * 搜索结束，deviceList.size()如果为0，则没有搜索到设备
		 * @param deviceList
		 */
		void onFoundFinish(List<BluetoothDevice> deviceList);
		/**
		 * 是否连接成功
		 * @param isConnected
		 */
		void onConnected(boolean isConnected, BluetoothDevice device);
		void onPower(String power);
		void onRunning(String running);
		void onMeasureError();
		void onMeasureResult(MeasurementResult result);
		void onDisconnected(BluetoothDevice device);
	}
	
}
