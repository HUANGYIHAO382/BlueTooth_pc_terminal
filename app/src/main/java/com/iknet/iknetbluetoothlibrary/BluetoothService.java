package com.iknet.iknetbluetoothlibrary;


import java.io.InputStream;
import java.util.Locale;

import com.iknet.iknetbluetoothlibrary.util.ClsUtils;

import android.annotation.SuppressLint;
import android.app.Service;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Message;
import android.telephony.PhoneStateListener;
import android.telephony.TelephonyManager;
import android.util.Log;
import android.widget.Toast;

/**
 * 蓝牙后台服务
 * 
 * @author www.1knet.com
 */
@SuppressLint("NewApi")
public class BluetoothService extends Service {
	private static final String TAG = "BluetoothService";
	
	public static final String ACTION_BLUETOOTH_DATA_WRITE = "com.action.ACTION_BLUETOOTH_DATA_WRITE";	//写入数据
	public static final String ACTION_MESSAGE_TOAST = "com.action.ACTION_MESSAGE_TOAST";
	public static final String ACTION_BLUETOOTH_DATA_EXTRA_BYTEARRAY = "com.action.ACTION_BLUETOOTH_DATA_EXTRA_BYTEARRAY";
	public static final String ACTION_BLUETOOTH_DATA_READ = "com.action.ACTION_BLUETOOTH_DATA_READ";	//读取数据
	public static final String ACTION_ERROR_MEASURE = "com.action.ACTION_ERROR_MEASURE";	//测量失败
	public static final String ACTION_BLUETOOTH_RUNNING = "com.action.ACTION_BLUETOOTH_RUNNING";
	public static final String ACTION_BLUETOOTH_POWER = "com.action.ACTION_BLUETOOTH_POWER";
	public static final String ACTION_BLUETOOTH_CONNECT = "com.action.ACTION_BLUETOOTH_CONNECT";
	public static final String ACTION_BLUETOOTH_CONNECT_EXTRA_BOOLEAN = "com.action.ACTION_BLUETOOTH_CONNECT_EXTRA_BOOLEAN";
	public static final String ACTION_BLUETOOTH_CONNECT2 = "com.action.ACTION_BLUETOOTH_CONNECT2";	//第二次握手
	public static final String ACTION_BT_CONNECT_TO = "com.action.ACTION_BT_CONNECT_TO";
	public static final String ACTION_BT_DISCONNECT_TO = "com.action.ACTION_BT_DISCONNECT_TO";

	public static String ConnectedBTAddress = null;

	public static boolean isSimulator = false;
	public static boolean enable = true;
	public static boolean enableBTDialog = true;
	public static InputStream is;
	
//	private BluetoothAdapter bluetoothAdapter = BluetoothAdapter.getDefaultAdapter();
	private String mAddr = "";
	private BluetoothDevice remoteDevice;
	private static final String pinStr = "0000";
	
	private BluetoothGATTConnModel bluetoothGATTConnModel;

	@Override
	public IBinder onBind(Intent intent) {
		return null;
	}
	
	@Override
	public void onCreate() {
		super.onCreate();
		Log.v(TAG, "onCreate");
		initPhoneStateListener();
		msgHandler = new MessageHandler();// 处理相关的消息Handler

		mBtMsgReceiver = new MessageReceiver();
		IntentFilter filter = new IntentFilter(ACTION_BLUETOOTH_DATA_WRITE);
		filter.addAction(BluetoothAdapter.ACTION_STATE_CHANGED);
		filter.addAction(BluetoothDevice.ACTION_ACL_DISCONNECTED);
		filter.addAction(BluetoothDevice.ACTION_BOND_STATE_CHANGED);
		filter.addAction(ACTION_BT_CONNECT_TO);
		filter.addAction(ACTION_BT_DISCONNECT_TO);
		registerReceiver(mBtMsgReceiver, filter);
	}

	@Override
	public int onStartCommand(Intent intent, int flags, int startId) {
		// LogX.e(this, "onStartCommand");
		int ret = super.onStartCommand(intent, flags, startId);
		if (intent == null) {
			stopSelf();
			return ret;
		}
		String addr = intent.getStringExtra("PREFS_BLUETOOTH_PRE_ADDR_STRING");
		if(addr.isEmpty()){
			Log.v(TAG, "蓝牙地址为空");
			this.stopSelf();
		}
		
		// BluetoothConnModel对象实例化
		if (mBluetoothConnModel == null) {
			mBluetoothConnModel = new BluetoothConnModel(this, msgHandler);
		}
		
		mAddr = addr;
		remoteDevice = BluetoothAdapter.getDefaultAdapter().getRemoteDevice(mAddr);// 获取远程蓝牙设备
		if(isSingleMode(remoteDevice)){
			//单模蓝牙直接连接
			connectTo();
		}else{
			pairTo();
		}

		return START_NOT_STICKY;// START_STICKY /* START_REDELIVER_INTENT */;;
	}

	@Override
	public void onDestroy() {
		super.onDestroy();
		Log.v(TAG, "onDestroy");
//		isConnect = false;
		sendConnectBroadcast(false);
		unregisterReceiver(mBtMsgReceiver);

		if (mBluetoothConnModel != null)
			mBluetoothConnModel.terminated();
		mBluetoothConnModel = null;
		// bluetoothGATTConnModel = null;

	}

	/**
	 * 广播蓝牙连接状态:连接成功、连接失败
	 */
//	public void postBTConnectState(boolean connect, String msg) {
//		if (connect) {
//			sendConnectBroadcast(true, msg); // 发送广播,连接成功
//		} else {
//			// if (connect != isConnect) {
//			// LogX.i(this, "连接失败：" + msg);
//			String sysLanguage = Locale.getDefault().getLanguage();
//			String str = "";
//			if (sysLanguage.equals("en")) {
//				str = "Device disconnected!";
//			} else {
//				str = "设备已断开！";
//			}
//			Toast.makeText(BluetoothService.this, str, Toast.LENGTH_SHORT).show();
//			sendConnectBroadcast(false, msg);
//			// }
//		}
////		isConnect = connect;
//	}

	/**************************************
	 * 蓝牙方案2
	 */
	public static final String REQUEST_ECHO_ACTION = "REQUEST_ECHO_ACTION";
	public static final String TOAST = "toast";
	public static final String GET_SERIVICE_STATUS_EVENT = "GET_SERIVICE_STATUS_EVENT";
	public static final String MONITOR_STATUS = "MONITOR_STATUS";
	public static final String TX_BYTES = "TX_BYTES";
	public static final String RX_BYTES = "RX_BYTES";

	private MessageReceiver mBtMsgReceiver;
	private BluetoothConnModel mBluetoothConnModel = null;
	private MessageHandler msgHandler;
//	private BluetoothDevice mDevice = null;

//	public static boolean isConnect = false;

	// Message types sent from the BluetoothChatService Handler
	public static final int MESSAGE_STATE_CHANGE = 1;
	public static final int MESSAGE_READ = 2;
	public static final int MESSAGE_WRITE = 3;
	public static final int MESSAGE_TOAST = 5;
	public static final int MESSAGE_ALERT_DIALOG = 6;
	public static final int MESSAGE_CONNECTED = 7;

	public static final int MSG_MODE_SEND_DATA = 0;
	public static final int MSG_MODE_SEND_STRING = 1;
	public static final int MSG_MODE_SEND_FILE = 2;
	
	public enum DeviceType{
		TYPE_88A,TYPE_9000
	}
	public static DeviceType connectedDeviceType;

	@SuppressLint("HandlerLeak")
	private class MessageHandler extends Handler {
//		public String deviceName = null;

		@Override
		public void handleMessage(Message msg) {

			switch (msg.what) {
			case MESSAGE_CONNECTED:
				//第一次握手成功
				Log.v(TAG, "第一次握手成功");
				String btName = (String) msg.obj;
				if(btName.length()>=6 && btName.substring(0, 6).equals("BP0542")){
					//9000类型设备不需要进行第二次握手
					connectedDeviceType = DeviceType.TYPE_9000;
					ConnectedBTAddress = mAddr;
				}else{
					connectedDeviceType = DeviceType.TYPE_88A;
				}
				sendConnectBroadcast(true); // 发送广播,连接成功
				break;
			case MESSAGE_WRITE:
				// 向蓝牙设备写入数据(指令)
				Intent intent2 = (Intent) msg.obj;
				postDataWrite(intent2);
				break;
//			case MESSAGE_STATE_CHANGE:
//
//				break;
			case MESSAGE_READ:
				// 当读取到蓝牙设备的数据时，在这里响应
				int flag = msg.arg1;
				int sflag = msg.arg2;
				byte[] dataBuff = (byte[]) msg.obj;
				postBTMsg(flag, sflag, dataBuff);
//				deviceName = null;
				break;
			case MESSAGE_TOAST:
//				Toast.makeText(getApplicationContext(),msg.getData().getString(TOAST), Toast.LENGTH_SHORT).show();
				Intent intent = new Intent(ACTION_MESSAGE_TOAST);
				getApplicationContext().sendBroadcast(intent);
				break;
			}
		}

//		private void sendBroadcast(String str, String action, int num) {
//			Intent i = new Intent(action);
//			i.putExtra("STR", str);
//			i.putExtra("COUNTER", num);
//			BluetoothService.this.sendBroadcast(i);
//		}
	}

	public class MessageReceiver extends BroadcastReceiver {
		@Override
		public void onReceive(Context context, Intent intent) {
			String action = intent.getAction();
			if (action.equals(ACTION_BLUETOOTH_DATA_WRITE)) {
				// 发送指令给血压计，每次发送间隔500ms
				msgHandler.sendMessageDelayed(msgHandler.obtainMessage(MESSAGE_WRITE, intent), 500);
			}else if (action.equals(BluetoothAdapter.ACTION_STATE_CHANGED)) {
				postStateChangeAction(context, intent);

			} else if (action.equals(BluetoothDevice.ACTION_ACL_DISCONNECTED)) {
				BluetoothDevice device = intent.getExtras().getParcelable(BluetoothDevice.EXTRA_DEVICE);
				disconnectTo();
				Log.v(TAG, "ACTION_ACL_DISCONNECTED-与" + device.getName() + "连接中断");
				// postBTConnectState(false,
				// BluetoothDevice.ACTION_ACL_DISCONNECTED);
				ConnectedBTAddress = null;
				stopSelf();
			} else if (action.equals(BluetoothDevice.ACTION_BOND_STATE_CHANGED)) {
				// 配对时状态变化
				remoteDevice = intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE);
				int bondState = intent.getIntExtra(BluetoothDevice.EXTRA_BOND_STATE, BluetoothDevice.BOND_NONE);
				if(bondState == BluetoothDevice.BOND_BONDED){
					Log.v(TAG, remoteDevice.getName() + "-绑定成功");
					connectTo();
				}else if(bondState == BluetoothDevice.BOND_BONDING){
					Log.v(TAG, remoteDevice.getName() + "-正在绑定..");
					if(isSingleMode(remoteDevice)){
//						remoteDevice.setPin(pinStrSingleMode.getBytes());
						connectTo();
					}else{
						remoteDevice.setPin(pinStr.getBytes());
					}
				}else if(bondState == BluetoothDevice.BOND_NONE){
					Log.v(TAG, remoteDevice.getName() + "-绑定失败");
					sendConnectBroadcast(false);
					
				}
			}else if(action.equals(ACTION_BT_CONNECT_TO)){
				if (mBluetoothConnModel == null) {
					mBluetoothConnModel = new BluetoothConnModel(BluetoothService.this, msgHandler);
				}
				String addr = intent.getStringExtra("addr");
				if(addr.isEmpty()){
					Log.v(TAG, "ACTION_CONNECT_TO:蓝牙地址为空");
					return;
				}
				mAddr = addr;
				remoteDevice = BluetoothAdapter.getDefaultAdapter().getRemoteDevice(mAddr);// 获取远程蓝牙设备
				if(isSingleMode(remoteDevice)){
					//单模蓝牙直接连接
					connectTo();
				}else{
					pairTo();
				}
			}else if(action.equals(ACTION_BT_DISCONNECT_TO)){
				//主动断开蓝牙连接
				disconnectTo();
			}
		}

	}
	
	private void pairTo(){
		if (remoteDevice.getBondState() != BluetoothDevice.BOND_BONDED) {
			//先配对，再连接蓝牙设备，这样系统就不会弹出匹配弹窗
			try {
				ClsUtils.createBond(remoteDevice.getClass(), remoteDevice);
			} catch (Exception e) {
				e.printStackTrace();
			}
		}else{
			connectTo();
		}
	}
	
	// 通过地址连接蓝牙设备
	private void connectTo() {
		Log.v(TAG, "connectTo:" + remoteDevice.getAddress());
		
		if(isSingleMode(remoteDevice)){
			//单模
			if(bluetoothGATTConnModel == null){
				bluetoothGATTConnModel = new BluetoothGATTConnModel(BluetoothService.this, msgHandler);
			}
			bluetoothGATTConnModel.connectTo(remoteDevice);
		}else{
			if (mBluetoothConnModel == null) {
				mBluetoothConnModel = new BluetoothConnModel(BluetoothService.this, msgHandler);
			}
			mBluetoothConnModel.connectTo(remoteDevice);
		}
		
	}
	
	/** 判断是否为单模蓝牙 */
	private boolean isSingleMode(BluetoothDevice bd){
		if(Build.VERSION.SDK_INT < Build.VERSION_CODES.KITKAT) return false;	//4.4以下不支持单模
		if(bd.getType() == BluetoothDevice.DEVICE_TYPE_LE){
			Log.v(TAG, "单模蓝牙");
			return true;
		}else{
			Log.v(TAG, "双模蓝牙");
			return false;
		}
	}
	
	private void postStateChangeAction(Context context, Intent intent) {
		int currentState = intent.getIntExtra(BluetoothAdapter.EXTRA_STATE,
				BluetoothAdapter.ERROR);
		switch (currentState) {
		case BluetoothAdapter.STATE_ON:
			// LogX.i(this, "[onReceive] current state = ON");
			break;
		case BluetoothAdapter.STATE_OFF:
			// LogX.i(this, "[onReceive] current state = OFF");
			try {
				BluetoothService.this.terminatedAllSockets();// 蓝牙关闭
			} catch (Exception e) {
				e.printStackTrace();
			}
			break;
		case BluetoothAdapter.STATE_TURNING_ON:
			// LogX.i(this, "[onReceive] current state = TURNING_ON");
			break;
		case BluetoothAdapter.STATE_TURNING_OFF:
			// LogX.i(this, "[onReceive] current state = TURNING_OFF");
			break;
		}
		// Log.i(TAG, "[onReceive] current state = "+currentState);
		// BluetoothConnController.this.disconnectTo(deviceAddress);
	}

	/*
	 * 向蓝牙发送数据
	 */
	private void postDataWrite(Intent intent) {
		// [-52, -52, 2,3, 1, 1, 0,-51]
		byte[] data = intent.getExtras().getByteArray(ACTION_BLUETOOTH_DATA_EXTRA_BYTEARRAY);
		if (data == null) {
			return;
		}
		if (data == null || data.length < 1)
			return;
		if(isSingleMode(remoteDevice)){
			if(bluetoothGATTConnModel == null) return;
			bluetoothGATTConnModel.writeCharacteristic(data);
		}else{
			if(mBluetoothConnModel == null) return;
			mBluetoothConnModel.writeToAllSockets(data);
		}
		
	}
	
	private void disconnectTo() {
		if(isSingleMode(remoteDevice)){
			if(bluetoothGATTConnModel == null){
				bluetoothGATTConnModel = new BluetoothGATTConnModel(this, msgHandler);
			}
			bluetoothGATTConnModel.disconnect();
		}else{
			if (mBluetoothConnModel == null) {
				mBluetoothConnModel = new BluetoothConnModel(this, msgHandler);
			}
			mBluetoothConnModel.disconnectSocketFromAddress(remoteDevice.getAddress());
		}
		
	}

	private void terminatedAllSockets() {
		// mConnService.terminated();
		mBluetoothConnModel.terminated();
		mBluetoothConnModel = null;
		// LogX.e(this, "terminatedAllSockets!!!");
		
	}

	/*************************************
	 * 蓝牙方案2 end
	 */

	/**
	 * 处理手机蓝牙接收到的数据
	 * @param flag
	 * @param sflag
	 * @param data
	 */
	private void postBTMsg(int flag, int sflag, byte[] data) {
		if(connectedDeviceType == DeviceType.TYPE_9000){
			if(flag == 1){
				if(sflag == 5){
					//实时压力值
					sendRunningBroadcast(((data[0]&0xFF)<<8) + (data[1]&0xFF));
				}else if(sflag == 6){
					//测量结果
					Log.v(TAG, "测量完成");
					getResult(data);
				}
			}
		}else if(connectedDeviceType == DeviceType.TYPE_88A){
			// 以下为6是发送广播， 如果是5的话可能会出现数据丢失。或者是其他原因导致数据丢失
			// byte swFlag = data[5];
			if (flag == 1) {
				// 血压测量操作
				if (sflag == 6) {
					// 发送过来的数据是测量结果
					Log.v(TAG, "测量完成");
					getResult(data);
					// sendBtDataBroadcast(data);
				} else if (sflag == 5) {
					// 发送过来的是测量过程中的数据
					if (data.length < 6) {
						return;
					}
					final int highflag = data[1] & 0xFF;
					final int lowflag = highflag ^ (data[4] & 0xFF);
					final int running = (highflag << 8) + lowflag;
					sendRunningBroadcast(running);
				} else if (sflag == 7) {
					sendErrorBroadcast();// 测量出现异常
				} else if (sflag == 1) {
					// 连接血压计应答
					int ans = data[0] & 0xFF;
					if (ans == 0) {
						ConnectedBTAddress = mAddr;
						sendConnect2Broadcast(true);
					} else {
						sendConnect2Broadcast(false);
					}
				} else if (sflag == 4) {
					// 关机应答
					Log.v(TAG, "关机应答" + (data[0] & 0xFF));
				}
			} else if (flag == 4) {
				// 查询操作
				if (sflag == 4) {
					// 接收到的数据是血压计的电量值
					int power = ((data[0] & 0xFF) << 8) + (data[1] & 0xFF);
					sendPowerBroadcast(power);
				}
			}
		}
		
		// sendBtDataBroadcast(data);
	}

	private void getResult(byte[] data) {
//		if(data.length > 7){
//			return;
//		}
//		byte orFlag = data[0];
//		byte yFlag = data[1];
//		byte mFlag = data[2];
//		byte dFlag = data[3];
//		byte hFlag = data[4];
//		byte nFlag = data[5];
//		byte seFlag = data[6];
		MeasurementResult result = new MeasurementResult();
		// if (orFlag == 0) {
		int math = (int) Math.pow(2, 8);
		// int oyear = yFlag;
		// int year = oyear + 2000;
		// int month = mFlag;
		// int day = dFlag;
		// int time = hFlag;
		// int min = nFlag;
		// int second = seFlag;
		// 收缩压
		int llow = (data[7] & 0xFF) * math + (data[8] & 0xFF);
		result.setCheckShrink(Math.abs(llow));// Math.abs
		// 舒张压
		int intszdatal = data[10] & 0xFF;
		result.setCheckDiastole(Math.abs(intszdatal));
		// 心率
		int heartRate = ((data[11] & 0xFF) << 4) + (data[12] & 0xFF);
		result.setCheckHeartRate(heartRate);
		Bundle bundle = new Bundle();
		bundle.putSerializable("result", result);
		Log.v(TAG, "测量结果-收缩压:" + result.getCheckShrink());
		if (remoteDevice != null) {
			result.setBluetoothName(remoteDevice.getName());
		}
		Intent intent = new Intent(ACTION_BLUETOOTH_DATA_READ);
		intent.putExtras(bundle);
		sendBroadcast(intent);
		// }
	}

	private void sendErrorBroadcast() {
		Intent intent = new Intent(ACTION_ERROR_MEASURE);
		sendBroadcast(intent);
	}

	private void sendRunningBroadcast(int running) {
		Intent intent = new Intent(ACTION_BLUETOOTH_RUNNING);
		intent.putExtra("running", String.valueOf(running));
		sendBroadcast(intent);
	}

	private void sendPowerBroadcast(int power) {
		Intent intent = new Intent(ACTION_BLUETOOTH_POWER);
		intent.putExtra("power", String.valueOf(power));
		sendBroadcast(intent);
	}

	/**
	 * 发送第一次握手是否成功的广播
	 * @param connect
	 */
	private void sendConnectBroadcast(boolean connect) {
		// stopSelf();
		Intent intent = new Intent(ACTION_BLUETOOTH_CONNECT);
		intent.putExtra(ACTION_BLUETOOTH_CONNECT_EXTRA_BOOLEAN, connect);
		sendBroadcast(intent);
	}
	
	/**
	 * 连接血压计响应是否成功
	 * @param connect
	 */
	private void sendConnect2Broadcast(boolean connect){
		Intent intent = new Intent(ACTION_BLUETOOTH_CONNECT2);
		intent.putExtra(ACTION_BLUETOOTH_CONNECT_EXTRA_BOOLEAN, connect);
		sendBroadcast(intent);
	}

	// 电话相关
	class MyPhoneStateListener extends PhoneStateListener {

		@Override
		public void onCallStateChanged(int state, String incomingNumber) {
			switch (state) {
			case TelephonyManager.CALL_STATE_IDLE: // 空闲
				// enable = true;
				break;
			case TelephonyManager.CALL_STATE_RINGING: // 来电
				// enable = false;
				Intent intent = new Intent("com.action.PHONE_IS_COMING");
				sendBroadcast(intent);
				break;
			case TelephonyManager.CALL_STATE_OFFHOOK: // 摘机（正在通话中）
				enable = false;
				break;
			}
		}
	}
	
	private void initPhoneStateListener() {
		// 获取电话通讯服务
		TelephonyManager tpm = (TelephonyManager) getSystemService(Context.TELEPHONY_SERVICE);
		// 创建一个监听对象，监听电话状态改变事件
		tpm.listen(new MyPhoneStateListener(),PhoneStateListener.LISTEN_CALL_STATE);
	}

}
