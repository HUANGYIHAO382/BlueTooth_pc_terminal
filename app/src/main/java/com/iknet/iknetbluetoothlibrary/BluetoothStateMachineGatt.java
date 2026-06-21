package com.iknet.iknetbluetoothlibrary;

import java.util.Collections;
import java.util.LinkedList;
import java.util.List;

import com.iknet.iknetbluetoothlibrary.model.ResultFromTurg;
import com.iknet.iknetbluetoothlibrary.util.FrameUtil;
import com.iknet.iknetbluetoothlibrary.util.LogUtil;

import android.util.Log;
import android.util.SparseArray;

public class BluetoothStateMachineGatt implements Runnable {
	private static final String TAG = "BlueToothStateMachineGatt";

	private static final int PRE_CODE1 = 0;// 前导码1
	private static final int PRE_CODE2 = 1;// 前导码2
	private static final int VER_CODE = 2;// 版本号
	private static final int LEN_CODE = 3;// 数据长度
	private static final int FLAG_CODE = 4;// 类型标记
	private static final int SFLAG_CODE = 5;// 类型子码
	private static final int DATA_CODE = 6;// 数据/参数
	private static final int CS_CODE = 7;// 校验码
	private static final byte HEADER_CODE1 = (byte) 0xAA;// 血压计发送的前导码
	private static final byte HEADER_CODE2 = (byte) 0x80;// 血压计发送的前导码
	
	private Thread thread;
	private BluetoothGATTConnModel mBtGattConnModel;
	private ResolveResultCallback mRRCallback;
	private SparseArray<IHandler> handlerMap = new SparseArray<IHandler>();
	private List<Byte> dataBytes = Collections.synchronizedList(new LinkedList<Byte>());	//要解析的数据
	private int status = PRE_CODE1;
	private byte[] mBuff = null;
	private int buffLength = 0;
	private int dataLength = 0;
	private int flag = 0;// 类型标记
	private int sflag = 0;// 类型子码
	private byte[] dataBuff = null;
	
	public BluetoothStateMachineGatt(BluetoothGATTConnModel btGattConnModel, ResolveResultCallback rrCallback){
		mBtGattConnModel = btGattConnModel;
		mRRCallback = rrCallback;
		thread = new Thread(this);
		// 只是进行了初始化，将相关的方法添加到handlerMap中，具体方法的执行要更具run()中的方法
		initReadHeader1();// 头
		initReadHeader2();
		initVerCode();
		initLenCode(); // 数据长度
		initFlagCode(); //
		initSFlagCode();
		initDataCode();
		initCSCode();
		Log.i(BluetoothConnModel.TAG,
				"------>[ConnectedThread] Constructure: Set up bluetooth socket i/o stream");
	}
	
	public void addData(byte[] buff){
		if(buff == null || buff.length == 0) return;
		StringBuffer sb = new StringBuffer();
		sb.append(FrameUtil.byte2hex(buff));
		Log.v(TAG, "" + sb.toString() + "，字节数量：" + sb.length()/2);
		
		
		for(int i=0; i<buff.length; i++){
			dataBytes.add(Byte.valueOf(buff[i]));
		}
		
	}
	
	/*private void initData() {
		// 前导码1
		int length = mBuff.length - buffLength;
		if(length >= 1){
			++buffLength;
		}else{
			return;
		}
		// 前导码2
		length = mBuff.length - buffLength;
		if(length >= 1){
			++buffLength;
		}else{
			return;
		}
		// 版本号
		length = mBuff.length - buffLength;
		if(length >= 1){
			++buffLength;
		}else{
			return;
		}
		// 数据长度
		length = mBuff.length - buffLength;
		if(length >= 1){
			dataLength = mBuff[buffLength] & 0xFF;
			++buffLength;
		}else{
			return;
		}
		// 类型标记
		length = mBuff.length - buffLength;
		if(length >= 1){
			flag = mBuff[buffLength] & 0xFF; // 获取指令的类型标记，用于确定指令的类型
			++buffLength;
			--dataLength;
		}else{
			return;
		}
		// 类型子码
		length = mBuff.length - buffLength;
		if(length >= 1){
			sflag = mBuff[buffLength] & 0xFF; // 获取指令的类型标记，用于确定指令的类型
			++buffLength;
			--dataLength;
		}else{
			return;
		}
		// 数据/参数
		length = mBuff.length - buffLength;
		if(dataLength>0 && length>=dataLength){
			dataBuff = new byte[dataLength];
			for(int i=0; i<dataLength; i++){
				++buffLength;
				dataBuff[i] = mBuff[buffLength-1];
			}
//			if(BaseApplication.debug){
//				if(sflag == 5){
//					Log.v(TAG, "发送过来的是测量过程中的数据：" + FrameUtil.byte2hex(dataBuff));
//				}else if(sflag == 6){
//					Log.v(TAG, "发送过来的数据是测量结果---->" + FrameUtil.byte2hex(dataBuff));
//				}else if(sflag == 1){
//					Log.v(TAG, "发送过来的是连接血压计应答：" + FrameUtil.byte2hex(dataBuff));
//				}
//			}
		}else{
			return;
		}
		// 校验码
		length = mBuff.length - buffLength;
		if(length >= 1){
			++buffLength;
		}else{
			return;
		}
	}*/
	
	
	private void initReadHeader1() {
		handlerMap.append(PRE_CODE1, new IHandler() {
			@Override
			public void handler() {
				try {
//					Log.v(TAG, "PRE_CODE1");
					if (dataBytes.size() >= 1) {
						byte[] buff = new byte[1];
						for(int i=0; i<buff.length; i++){
							buff[i] = dataBytes.get(0).byteValue();
							dataBytes.remove(0);
						}

						if (HEADER_CODE1 == buff[0]) {
							status = PRE_CODE2;
						}
					} else {
						Thread.sleep(200);
					}
				} catch (Exception e) {
					status = PRE_CODE1;
					e.printStackTrace();
				}
			}
		});
	}
	
	private void initReadHeader2() {
		handlerMap.append(PRE_CODE2, new IHandler() {

			@Override
			public void handler() {
				try {
					if (dataBytes.size() >= 1) {
						byte[] buff = new byte[1];
						for(int i=0; i<buff.length; i++){
							buff[i] = dataBytes.get(0).byteValue();
							dataBytes.remove(0);
						}
						if (HEADER_CODE2 == buff[0]) {
							status = VER_CODE;
						}else{
							status = PRE_CODE1;
						}
					}
				} catch (Exception e) {
					status = PRE_CODE1;
					e.printStackTrace();
				}
			}
		});
	}
	
	private void initVerCode() {
		handlerMap.append(VER_CODE, new IHandler() {

			@Override
			public void handler() {
				try {
					if (dataBytes.size() >= 1) {
						byte[] buff = new byte[1];
						for(int i=0; i<buff.length; i++){
							buff[i] = dataBytes.get(0).byteValue();
							dataBytes.remove(0);
						}
						status = LEN_CODE;
					}
				} catch (Exception e) {
					status = PRE_CODE1;
					e.printStackTrace();
				}
			}
		});
	}
	
	/**
	 * 数据长度
	 */
	private void initLenCode() {
		handlerMap.append(LEN_CODE, new IHandler() {

			@Override
			public void handler() {
				try {
					if (dataBytes.size() >= 1) {
						byte[] buff = new byte[1];
						for(int i=0; i<buff.length; i++){
							buff[i] = dataBytes.get(0).byteValue();
							dataBytes.remove(0);
						}
						dataLength = buff[0] & 0xFF;
						status = FLAG_CODE;
					}
				} catch (Exception e) {
					status = PRE_CODE1;
					e.printStackTrace();
				}
			}
		});
	}

	private void initFlagCode() {
		handlerMap.append(FLAG_CODE, new IHandler() {

			@Override
			public void handler() {
				try {
					if (dataBytes.size() >= 1) {
						byte[] buff = new byte[1];
						for(int i=0; i<buff.length; i++){
							buff[i] = dataBytes.get(0).byteValue();
							dataBytes.remove(0);
						}
						dataLength--;
						flag = buff[0] & 0xFF;// 获取指令的类型标记，用于确定指令的类型
						status = SFLAG_CODE;
					}
				} catch (Exception e) {
					status = PRE_CODE1;
					e.printStackTrace();
				}
			}
		});
	}
	
	private void initSFlagCode() {
		handlerMap.append(SFLAG_CODE, new IHandler() {

			@Override
			public void handler() {
				try {
					if (dataBytes.size() >= 1) {
						byte[] buff = new byte[1];
						for(int i=0; i<buff.length; i++){
							buff[i] = dataBytes.get(0).byteValue();
							dataBytes.remove(0);
						}
						dataLength--;
						sflag = buff[0] & 0xFF;// 获取类型子码，类型子码是对指令类型的进一步说明
						status = DATA_CODE;
					}
				} catch (Exception e) {
					status = PRE_CODE1;
					e.printStackTrace();
				}
			}
		});
	}
	
	/**
	 * 数据/参数
	 */
	private void initDataCode() {
		handlerMap.append(DATA_CODE, new IHandler() {

			@Override
			public void handler() {
				try {
//					Log.v(TAG, "DATA_CODE");
					if (dataLength > 0 && dataBytes.size() >= dataLength) {
						// 存储数据的数组，需要的数据存储在这里
						dataBuff = new byte[dataLength];
						for(int i=0; i<dataBuff.length; i++){
							dataBuff[i] = dataBytes.get(0).byteValue();
							dataBytes.remove(0);
						}
//						if(dataBuffBefore != null){
//							isDataSame = dataBuffBefore.equals(dataBuff);
//						}
//						dataBuffBefore = dataBuff;
						if(LogUtil.debug){
							if(sflag == 5){
								Log.v(TAG, "发送过来的是测量过程中的数据：" + FrameUtil.byte2hex(dataBuff));
							}else if(sflag == 6){
								Log.v(TAG, "发送过来的数据是测量结果---->" + FrameUtil.byte2hex(dataBuff));
							}else if(sflag == 1){
								Log.v(TAG, "发送过来的是连接血压计应答：" + FrameUtil.byte2hex(dataBuff));
							}
						}
						status = CS_CODE;
					}
				} catch (Exception e) {
					status = PRE_CODE1;
					e.printStackTrace();
				}
			}
		});
	}
	
//	void digui(int i){
//		if(i>0){
//			digui(i-1);
//			Log.v(TAG, ""+i);
//		}
//	}

	/**
	 * 校验码
	 */
	private void initCSCode() {
		handlerMap.append(CS_CODE, new IHandler() {

			@Override
			public void handler() {
//				if(isDataSame){
//					return;
//				}
				try {
					if (dataBytes.size() >= 1) {
						byte[] buff = new byte[1];
						for(int i=0; i<buff.length; i++){
							buff[i] = dataBytes.get(0).byteValue();
							dataBytes.remove(0);
						}
						// 将数据返回给响应的地方
//						mHandler.obtainMessage(BluetoothService.MESSAGE_READ, flag, sflag, dataBuff).sendToTarget();
						ResultFromTurg resultFromTurg = new ResultFromTurg();
						resultFromTurg.setFlag(flag);
						resultFromTurg.setSflag(sflag);
						resultFromTurg.setDataBuff(dataBuff);
						mRRCallback.onResolveResult(resultFromTurg);
					}
				} catch (Exception e) {
					e.printStackTrace();
				} finally {
					status = PRE_CODE1;
				}
			}
		});
	}
	
	@Override
	public void run() {
		while (mBtGattConnModel.isConnected()) {
			// 当蓝牙处于连接状态时，循环进行如下操作
			IHandler handler = handlerMap.get(status);
			if (handler != null)
				handler.handler();
		}
	}
	
	public void start(){
		if(thread != null && !thread.isAlive()){
			thread.start();
		}
	}
	
	public interface ResolveResultCallback{
		void onResolveResult(ResultFromTurg result);
	}
	
}
