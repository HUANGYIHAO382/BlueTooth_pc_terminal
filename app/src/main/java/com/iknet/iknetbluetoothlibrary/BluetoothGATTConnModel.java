package com.iknet.iknetbluetoothlibrary;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import android.annotation.SuppressLint;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothProfile;
import android.content.Context;
import android.os.Handler;
import android.util.Log;

import com.iknet.iknetbluetoothlibrary.BluetoothStateMachineGatt.ResolveResultCallback;
import com.iknet.iknetbluetoothlibrary.model.ResultFromTurg;
import com.iknet.iknetbluetoothlibrary.util.FrameUtil;


@SuppressLint("NewApi")
public class BluetoothGATTConnModel {
	private static final String TAG = "BluetoothGATTConnModel";
	
	private UUID uuidService, uuidCharacteristicRead, uuidCharacteristicWrite;
	private static boolean isConnected = false;	//是否已连接
	private Handler mHandler;
	private Context mContext;
	private BluetoothStateMachineGatt btStateMachineGatt;
	
	private BluetoothGatt bluetoothGatt;
	private BluetoothDevice mRemoteDevice;
//	private List<BluetoothGattCharacteristic> characteristicReads = new ArrayList<>();
	private BluetoothGattCharacteristic characteristicRead;
	private BluetoothGattCharacteristic characteristicWrite;

	public BluetoothGATTConnModel(Context context, Handler handler) {
//		bluetoothAdapter = BluetoothAdapter.getDefaultAdapter();
		mHandler = handler;
		mContext = context;
		
		if(btStateMachineGatt == null){
			btStateMachineGatt = new BluetoothStateMachineGatt(this, new ResolveResultCallback() {
				@Override
				public void onResolveResult(ResultFromTurg result) {
					mHandler.obtainMessage(BluetoothService.MESSAGE_READ,
							result.getFlag(), result.getSflag(), result.getDataBuff()).sendToTarget();
				}
			});
			
		}

	}

	public void connectTo(final BluetoothDevice remoteDevice) {
		if(remoteDevice == null) return;
		//延时连接，防止蓝牙服务还未绑定起来，就连接，导致异常
//		new Handler().postDelayed(new Runnable() {
//			
//			@Override
//			public void run() {
				if(mRemoteDevice != null && mRemoteDevice.equals(remoteDevice) && BluetoothService.ConnectedBTAddress != null){
					//已连接该设备，直接测量
					mHandler.obtainMessage(BluetoothService.MESSAGE_CONNECTED, -1, -1,
							mRemoteDevice.getName()).sendToTarget();
				}else{
					bluetoothGatt = remoteDevice.connectGatt(mContext, true, bluetoothGattCallback);
					mRemoteDevice = remoteDevice;
				}
//			}
//		}, 500);
		
	}
	
	public void disconnect(){
		if(bluetoothGatt != null){
			bluetoothGatt.disconnect();
			bluetoothGatt.close();
			bluetoothGatt = null;
		}

//		readThread.stopRead();
	}
	
	private BluetoothGattCallback bluetoothGattCallback = new BluetoothGattCallback() {
		@Override
		public void onConnectionStateChange(BluetoothGatt gatt, int status, int newState) {
			String name = gatt.getDevice().getName();
			if(newState == BluetoothProfile.STATE_CONNECTED){
//				Log.v(TAG, "成功连接该蓝牙设备：" + name);
				Log.v(TAG, "启动发现服务:" + bluetoothGatt.discoverServices());
				
			}else if(newState == BluetoothProfile.STATE_DISCONNECTED){
				Log.v(TAG, "断开连接：" + name);
				isConnected = false;
			}
//			if(status == BluetoothGatt.GATT_SUCCESS){
//				Log.v(TAG, "onConnectionStateChange:启动服务成功");
//			}
		};

		private final String UUID_SERVICE = "0000fff0-0000-1000-8000-00805f9b34fb";
		private final String UUID_CHARACTERISTIC_NOTIFY = "0000fff1-0000-1000-8000-00805f9b34fb";
		private final String UUID_CHARACTERISTIC_WRITE = "0000fff2-0000-1000-8000-00805f9b34fb";
		@Override
		public void onServicesDiscovered(BluetoothGatt gatt, int status) {
			if(status == BluetoothGatt.GATT_SUCCESS){
				Log.v(TAG, "onServicesDiscovered:启动服务成功");
				isConnected = true;
				btStateMachineGatt.start();
				//找到可用的service和characteristic
				exit:
				for(BluetoothGattService s : gatt.getServices()){
					Log.d(TAG, "Service-uuid:" + s.getUuid() +",string:" + s.toString());
					if(!UUID_SERVICE.equals(s.getUuid().toString())) continue;

					int charaSize = s.getCharacteristics().size();
					if(charaSize < 1) continue;
					characteristicRead = null;
					characteristicWrite = null;
					for(int i=0; i<charaSize; i++){
						BluetoothGattCharacteristic c = s.getCharacteristics().get(i);
						Log.d(TAG, "characteristic-uuid:" + c.getUuid() +",properties:" + c.getProperties());
//						if(c.getDescriptors() != null && c.getDescriptors().size() != 0){
						if(characteristicWrite == null && UUID_CHARACTERISTIC_WRITE.equals(c.getUuid().toString())){
							characteristicWrite = c;
						}
						if(characteristicRead == null && UUID_CHARACTERISTIC_NOTIFY.equals(c.getUuid().toString())){
							characteristicRead = c;
						}
//						}
						if(characteristicRead != null && characteristicWrite != null) break exit;
					}
				}
				/*for(BluetoothGattService s : gatt.getServices()){
					Log.d(TAG, "Service-uuid:" + s.getUuid() +",string:" + s.toString());
					int charaSize = s.getCharacteristics().size();
					if(charaSize < 1) continue;
					characteristicRead = null;
					characteristicWrite = null;
					for(int i=0; i<charaSize; i++){
						BluetoothGattCharacteristic c = s.getCharacteristics().get(i);
						Log.d(TAG, "characteristic-uuid:" + c.getUuid() +",properties:" + c.getProperties());
//						if(c.getDescriptors() != null && c.getDescriptors().size() != 0){
							if(characteristicWrite == null && isCharacteristicWritable(c)){
								characteristicWrite = c;
							}
							if(characteristicRead == null && isCharacteristicNotifiable(c)){
								characteristicRead = c;
							}
//						}
						if(characteristicRead != null && characteristicWrite != null) break exit;
					}
				}*/
				if(characteristicRead != null && characteristicWrite != null){
					gatt.setCharacteristicNotification(characteristicRead, true);
					mHandler.obtainMessage(BluetoothService.MESSAGE_CONNECTED, -1, -1,
							mRemoteDevice.getName()).sendToTarget();
				}else{
					Log.v(TAG, "未找到可用的characteristic");
					disconnect();
				}
				
			}else if(status == BluetoothGatt.GATT_FAILURE){
				Log.v(TAG, "启动服务失败");
				isConnected = false;
			}
		};
		
		@Override
		public void onCharacteristicChanged(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic) {
			byte[] buff = characteristic.getValue();
			Log.v(TAG, "onCharacteristicChanged:" + FrameUtil.byte2hex(buff) + ",字节个数：" + buff.length);
			btStateMachineGatt.addData(buff);
		};
		
		@Override
		public void onCharacteristicWrite(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic, int status) {
			if(status == BluetoothGatt.GATT_SUCCESS){
				Log.v(TAG, "写入成功：" + FrameUtil.byte2hex(characteristic.getValue()));
			}else if(status == BluetoothGatt.GATT_FAILURE){
				Log.v(TAG, "写入失败：" + FrameUtil.byte2hex(characteristic.getValue()));
			}
		};
		
		@Override
		public void onCharacteristicRead(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic, int status) {
//			if (status == BluetoothGatt.GATT_SUCCESS) {
//				byte[] buff = characteristic.getValue();
//				Log.v(TAG, "onCharacteristicRead:" + FrameUtil.byte2hex(buff) + ",字节个数：" + buff.length);
//				btStateMachineGatt.addData(buff);
//			}
		};
		
	};

	// 检查特征是否支持通知
	private boolean isCharacteristicNotifiable(BluetoothGattCharacteristic characteristic) {
		boolean notify = (characteristic.getProperties() &
				(BluetoothGattCharacteristic.PROPERTY_NOTIFY |
						BluetoothGattCharacteristic.PROPERTY_INDICATE)) != 0;
		Log.d(TAG, "isCharacteristicNotifiable-uuid:"+characteristic.getUuid()+",notify:" + notify);
		return notify;
	}

	private boolean isCharacteristicWritable(BluetoothGattCharacteristic characteristic) {
		boolean writeable = (characteristic.getProperties() &
				(BluetoothGattCharacteristic.PROPERTY_WRITE)) != 0;
		Log.d(TAG, "isCharacteristicWritable-uuid:"+characteristic.getUuid()+",writeable:" + writeable);
		return writeable;
	}

	public void writeCharacteristic(byte[] data){
		if(characteristicWrite == null || data == null) return;
		Log.v(TAG, "写入数据：" + FrameUtil.byte2hex(data));
		
		characteristicWrite.setValue(data);
//		characteristicWrite.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT);
		boolean w = bluetoothGatt.writeCharacteristic(characteristicWrite);
		Log.v(TAG, "写入操作：" + w);
		if(!w){
			disconnect();
		}
		
	}
	
	public boolean isConnected(){
		return isConnected;
	}
	
	public interface MyBluetoothGattCallback{
		void onConnectionStateChange(int status, int newState);
		void onServicesDiscovered(int status);
	}

}
