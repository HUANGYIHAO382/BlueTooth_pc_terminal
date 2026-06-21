package com.iknet.iknetbluetoothlibrary;


import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

import android.bluetooth.BluetoothSocket;
import android.os.Handler;
import android.util.Log;
import android.util.SparseArray;

/**
 * 对接收到的设备数据进行解析
 * 
 * @author www.1knet.com
 * 
 */
public class BlueToothStateMachine implements Runnable {
	private static final String TAG = "BlueToothStateMachine";

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

	private Thread thread = null;
	private BluetoothSocketConfig socketConfig;
	private BluetoothSocket mmSocket;
	private Handler mHandler;
	private InputStream inStream;
	private OutputStream outStream;
	private SparseArray<IHandler> handlerMap = new SparseArray<IHandler>();
	private int status = PRE_CODE1;
	// private int version = 0;
	private int dataLength = 0;
	private int flag = 0;// 类型标记
	private int sflag = 0;// 类型子码
	private byte[] dataBuff = null;
	private byte[] dataBuffBefore = null;
	private boolean isDataSame = false;
	private int readTimeout = 0;

	public BlueToothStateMachine(BluetoothSocketConfig socketConfig,
			BluetoothSocket mmSocket, Handler mHandler) {
		try {
			this.thread = new Thread(this, mmSocket.getRemoteDevice()
					.toString());
			this.socketConfig = socketConfig;
			this.mmSocket = mmSocket;
			this.mHandler = mHandler;
			// 先判断isStream的长度，再进行数据的读取？？？？？读取的时候是读取具体位的数据，不是从头开始读取
			this.inStream = mmSocket.getInputStream();// 这里获取的不是一个特定的流，而是持续的流？？？
			this.outStream = mmSocket.getOutputStream();//
			// 只是进行了初始化，将相关的方法添加到handlerMap中，具体方法的执行要更具run()中的方法
			initReadHeader1();// 头
			initPreCode2();
			initVerCode();
			initLenCode(); // 数据长度
			initFlagCode(); //
			initSFlagCode();
			initDataCode();
			initCSCode();
			Log.i(BluetoothConnModel.TAG,
					"------>[ConnectedThread] Constructure: Set up bluetooth socket i/o stream");
		} catch (IOException e) {
			Log.e(BluetoothConnModel.TAG,
					"------>[ConnectedThread] temp sockets not created", e);
		}
	}
	
	private void initReadHeader1() {
		handlerMap.append(PRE_CODE1, new IHandler() {
			@Override
			public void handler() {
				try {
//					Log.v(TAG, "获取数据的字节长度：" + inStream.available());
					if (inStream.available() >= 1) {
						byte[] buff = new byte[1];
						inStream.read(buff);

						// read(buff ,len);
						// LogX.e(this, buff);
						if (HEADER_CODE1 == buff[0]) {
							// success read pre code.
							status = PRE_CODE2;
						}
					} else {
						Thread.sleep(10);
					}
				} catch (IOException e) {
					status = PRE_CODE1;
					e.printStackTrace();
				} catch (InterruptedException e) {
					status = PRE_CODE1;
					e.printStackTrace();
				}
			}
		});
	}
	
	private void initPreCode2() {
		handlerMap.append(PRE_CODE2, new IHandler() {

			@Override
			public void handler() {
				try {
					if (inStream.available() >= 1) {
						byte[] buff = new byte[1];
						inStream.read(buff);
						// LogX.e(this, buff);
						if (HEADER_CODE2 == buff[0]) {
							status = VER_CODE;
						}
					}
				} catch (IOException e) {
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
					if (inStream.available() >= 1) {
						byte[] buff = new byte[1];
						inStream.read(buff);
						// version = buff[0] & 0xFF;
						status = LEN_CODE;
						// LogX.e(this, buff);
					}
				} catch (IOException e) {
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
					if (inStream.available() >= 1) {
						byte[] buff = new byte[1];
						inStream.read(buff);
						dataLength = buff[0] & 0xFF;
						status = FLAG_CODE;
						// LogX.e(this, buff);
					}
				} catch (IOException e) {
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
					if (inStream.available() >= 1) {
						byte[] buff = new byte[1];
						inStream.read(buff);
						dataLength--;
						flag = buff[0] & 0xFF;// 获取指令的类型标记，用于确定指令的类型
						status = SFLAG_CODE;
						// LogX.e(this, buff);
					}
				} catch (IOException e) {
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
					if (inStream.available() >= 1) {
						byte[] buff = new byte[1];
						inStream.read(buff);
						dataLength--;
						sflag = buff[0] & 0xFF;// 获取类型子码，类型子码是对指令类型的进一步说明
						status = DATA_CODE;
					}
				} catch (IOException e) {
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
					if (dataLength > 0 && inStream.available() >= dataLength) {
						// 存储数据的数组，需要的数据存储在这里
						dataBuff = new byte[dataLength];
						inStream.read(dataBuff);
						// LogX.e(this, dataBuff);
						if(dataBuffBefore != null){
							isDataSame = dataBuffBefore.equals(dataBuff);
						}
						dataBuffBefore = dataBuff;
					}
					status = CS_CODE;
				} catch (IOException e) {
					status = PRE_CODE1;
					e.printStackTrace();
				}
			}
		});
	}

	/**
	 * 校验码
	 */
	private void initCSCode() {
		handlerMap.append(CS_CODE, new IHandler() {

			@Override
			public void handler() {
				if(isDataSame){
					return;
				}
				try {
					if (inStream.available() >= 1) {
						byte[] buff = new byte[1];
						inStream.read(buff);
						// LogX.e(this, buff);
						// send message to activity handle.
						// flag, sflag, dataBuff
						// 将数据返回给响应的地方
						mHandler.obtainMessage(BluetoothService.MESSAGE_READ,
								flag, sflag, dataBuff).sendToTarget();
					}
				} catch (IOException e) {
					// TODO Auto-generated catch block
					e.printStackTrace();
				} finally {
					status = PRE_CODE1;
				}
			}
		});
	}

	@Override
	public void run() {
		while (socketConfig.isSocketConnected(mmSocket)) {
			// 当蓝牙处于连接状态时，循环进行如下操作
			IHandler handler = handlerMap.get(status);
			if (handler != null)
				handler.handler();
//			try {
//				if(status == PRE_CODE1){
//					Thread.sleep(50);	//每次查询的时间间隔
//				}
//			} catch (InterruptedException e) {
//				e.printStackTrace();
//			}
		}
	}

	public boolean write(byte[] buff) {
		try {
			outStream.write(buff);
			return true;
		} catch (IOException e) {
			// TODO Auto-generated catch block
			Log.i(TAG, "------写入错误的原因----->" + e.getMessage());
			e.printStackTrace();
		}
		return false;
	}

	public void start() {
		this.thread.start();
	}

	public void setReadTimeout(int millis) {
		this.readTimeout = millis;
	}

	public int getReadTimeout() {
		return this.readTimeout;
	}
}
