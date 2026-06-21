package com.iknet.iknetbluetoothlibrary;
/*
 * Copyright (C) 2011 Wireless Network and Multimedia Laboratory, NCU, Taiwan
 * 
 * You can reference http://wmlab.csie.ncu.edu.tw
 * 
 * This class is used to process connection operation, including server side or client side. * 
 * 
 * @author Fiona
 * @version 0.0.1
 *
 */



import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.lang.reflect.Method;
import java.util.Set;
import java.util.UUID;

import android.annotation.SuppressLint;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothServerSocket;
import android.bluetooth.BluetoothSocket;
import android.content.Context;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Message;
import android.os.ParcelUuid;
import android.util.Log;

@SuppressLint("NewApi")
public class BluetoothConnModel {
	private static final boolean D = true;
	static final String TAG = "BluetoothConnModel";
	private static final String NAME = "BluetoothConn";
	public static final UUID CUSTOM_UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB");
	// 00001101-0000-1000-8000-00805F9B34FB
	// private static final UUID CUSTOM_UUID =
	// UUID.fromString("abbcddef-abc0-abc0-abc0-aaaaaaaaaaaa");
	// ca3e49b2-d1cc-4607-a705-4061f51a5591
	// private static final UUID CUSTOM_UUID = UUID
	// .fromString("8ce255c0-200a-11e0-ac64-0800200c9a66");
	public static final String MONITOR_OUTPUT_NAME = "output.txt";

	private final BluetoothAdapter mAdapter;
	private final Handler mHandler;
//	private final Context mContext;
	// private Map<BluetoothDevice, BluetoothSocketConfig> mBluetoothSocekts;
	private ServerSocketThread mServerSocketThread;
	private BluetoothSocketConfig mSocketConfig = null;
	private FileOutputStream mOutputFile;
	private boolean mMonitor = false;
	private int mTxBytes = 0;
	private int mRxBytes = 0;
	// private int mMonitorBytes = 0;
//	private int connectTimes = 0;// 连接的次数
//	private boolean connectedFlag = false;// 是否连接
	private BluetoothDevice mBluetoothDevice;

	public int getTxBytes() {
		return mTxBytes;
	}

	public int getRxBytes() {
		return mRxBytes;
	}

	public boolean getFileMonitor() {
		return mMonitor;
	}

	public void startFileMonitor(boolean b) {
		Log.d(TAG, "startFileMonitor " + b);
		mMonitor = b;
		if (mMonitor == true) {
			File root = Environment.getExternalStorageDirectory();
			try {
				mOutputFile = new FileOutputStream(root + "/"
						+ MONITOR_OUTPUT_NAME, false);
			} catch (Exception e) {
				Log.e(TAG, "new FileOutputStream fail", e);
			}
		} else {
			try {
				mOutputFile.close();
			} catch (Exception e) {

			}
		}
	}

	public BluetoothConnModel(Context context, Handler handler) {
		mAdapter = BluetoothAdapter.getDefaultAdapter();
		mHandler = handler;
//		mContext = context;
		// mBluetoothSocekts = new HashMap<BluetoothDevice,
		// BluetoothSocketConfig> ();

		// 获取BluetoothSocketConfig实例化对象
		mSocketConfig = BluetoothSocketConfig.getInstance();
	}

	public synchronized void startSession() {
		if (D)
			Log.d(TAG, "---->[startSession] ServerSocketThread start...");

		if (mServerSocketThread == null) {
			Log.v(TAG, "---->[startSession] mServerSocketThread is dead");
			mServerSocketThread = new ServerSocketThread();
			mServerSocketThread.start();
		} else {
			Log.v(TAG, "---->[startSession] mServerSocketThread is alive : "
					+ this);
		}

		// mSocketConfig = BluetoothSocketConfig.getInstance();
	}

	public synchronized void connectTo(BluetoothDevice device) {
//		mHandler.sendMessage(mHandler.obtainMessage(BluetoothService.MESSAGE_GATT_CONNECTION));
		mBluetoothDevice = device;
		if (D)
			Log.d(TAG, "---->[connectTo] ClientSocketThread start...");
		SocketThread mSocketThread = new SocketThread(device);
		mSocketThread.start();
	}

	/**
	 * 连接成功后执行的操作
	 * @param socket
	 */
	public synchronized void connected(BluetoothSocket socket) {
		Log.v(TAG, "成功连接设备：" + mBluetoothDevice.getName() +"," + mBluetoothDevice.getAddress());
		// BluetoothSocketConfig socketConfig = new BluetoothSocketConfig();
		
		mHandler.obtainMessage(BluetoothService.MESSAGE_CONNECTED, -1, -1, 0+"").sendToTarget();

		// 连接上之后就可以监听数据了，启动线程 BlueToothStateMachine connectedThread
		BlueToothStateMachine connectedThread = new BlueToothStateMachine(
				mSocketConfig, socket, mHandler);

		// 这里用到了BluetoothSocketConfig类中的参数,添加socket信息
		if (mSocketConfig.registerSocket(socket, connectedThread,
				BluetoothSocketConfig.SOCKET_CONNECTED) == false) {

			mHandler.obtainMessage(BluetoothService.MESSAGE_ALERT_DIALOG, -1,
					-1, "Device link back again!").sendToTarget();
		}
		Log.e(TAG, "---->[connected] connectedThread hashcode = "
				+ connectedThread.toString());
		connectedThread.start();
	}

	// 往特定socket里面写数据
	public void writeToSocket(BluetoothSocket socket, byte[] data) {
		if (D)
			Log.d(TAG, "---->writeToDevice start...");
		BlueToothStateMachine connectedThread = mSocketConfig.getConnectedThread(socket);
		Log.e(TAG, "---->[writeToDevice] connectedThread hashcode = " + connectedThread.toString());
		if (mSocketConfig.isSocketConnected(socket)) {
			Log.w(TAG, "---->[writeToDevice] The socket is alived.");
			boolean flag = connectedThread.write(data);
			Log.v(TAG, "-----指令写入情况---->" + flag);
		} else
			Log.w(TAG, "---->[writeToDevice] The socket has been closed.");
	}

	/*
	 * 发送数据
	 */
	public void writeToAllSockets(byte[] data) {
		if (D)
			Log.d(TAG, "---->writeToAllDevices start...");
		for (BluetoothSocket socket : mSocketConfig.getConnectedSocketList()) {
			synchronized (this) {
				// if (mState != STATE_CONNECTED) return;
				writeToSocket(socket, data);

				Log.e(TAG, "---->[writeToAllDevices] currentTimeMillis: "
						+ System.currentTimeMillis());
			}
		}
	}

	public void disconnectServerSocket() {
		Log.d(TAG, "---->[disconnectServerSocket]---->");
		/*
		 * try { serverSocket.close(); Log.w(TAG,
		 * "[disconnectServerSocket] Close "+serverSocket.toString()); } catch
		 * (IOException e) { Log.e(TAG, "close() of server failed", e); }
		 */
		if (mServerSocketThread != null) {
			mServerSocketThread.disconnect();
			mServerSocketThread = null;
			Log.w(TAG, "---->[disconnectServerSocket] NULL mServerSocketThread");
		}
	}

	public void disconnectSocketFromAddress(String address) {
		Set<BluetoothSocket> socketSets = mSocketConfig.containSockets(address);
		for (BluetoothSocket socket : socketSets) {
			disconnectSocket(socket);
		}
	}

	public synchronized void disconnectSocket(BluetoothSocket socket) {
		Log.w(TAG, "---->[disconnectSocket]---->" + socket.toString()
				+ " ; device name is " + socket.getRemoteDevice().getName());
		if (!mSocketConfig.isSocketConnected(socket)) {
			// XXX: it always jump to here while disconnected due to exception
			Log.w(TAG,
					"---->[disconnectSocket] mSocketConfig doesn't contain the socket: "
							+ socket.toString() + " ; device name is "
							+ socket.getRemoteDevice().getName());
			return;
		}
		// BluetoothSocket bluetoothSocket =
		// mBluetoothSocekts.get(device).getBluetoothSocket();
		Log.d(TAG, socket.getRemoteDevice().getName()
				+ " connection was disconnected!");
		// notifyUiFromToast(socket.getRemoteDevice().getName()+" connection was lost");
		mSocketConfig.unregisterSocket(socket);
	}

	public void terminated() {
		Log.w(TAG, "---->[terminated]--------------");

		disconnectServerSocket();
		for (BluetoothSocket socket : mSocketConfig.getConnectedSocketList()) {
			Log.w(TAG, "[terminated] Left Socket(s): "
					+ mSocketConfig.getConnectedSocketList().size());
			disconnectSocket(socket);
		}
		/*
		 * if (mSocketConfig.getConnectedSocketList().size()>0) { try {
		 * mBluetoothSocekts.clear(); }catch(UnsupportedOperationException e) {
		 * Log.v(TAG, "[terminated] Clear Socket Map error."); } }
		 */
		Log.w(TAG, "---->[terminated] Final Left Socket(s): "
				+ mSocketConfig.getConnectedSocketList().size());
	}

	private void notifyUiFromToast(String str) {
		Message msg = mHandler.obtainMessage(BluetoothService.MESSAGE_TOAST);
		Bundle bundle = new Bundle();
		bundle.putString(BluetoothService.TOAST, str);
		msg.setData(bundle);
		mHandler.sendMessage(msg);
	}
	
	private static boolean shouldUseFixChannel() {
		if (Build.VERSION.RELEASE.startsWith("4.0.")) {
			if (Build.MANUFACTURER.equals("samsung")) {
				return true;
			}
			if (Build.MANUFACTURER.equals("HTC")) {
				return true;
			}
		}
		if (Build.VERSION.RELEASE.startsWith("4.1.")) {
			if (Build.MANUFACTURER.equals("samsung")) {
				return true;
			}
		}
		if (Build.MANUFACTURER.equals("Xiaomi")) {
			if (Build.VERSION.RELEASE.equals("2.3.5")) {
				return true;
			}
		}
		return false;
	}

	/*
	 * Connecting as a server
	 */
	private class ServerSocketThread implements Runnable {
		private BluetoothServerSocket mmServerSocket = null;
		private Thread thread = null;
		private boolean isServerSocketValid = false;

		// private final ExecutorService pool;
		@SuppressLint("NewApi")
		public ServerSocketThread() {
			this.thread = new Thread(this);

			BluetoothServerSocket serverSocket = null;
			try {
				Log.v(TAG,
						"---->[ServerSocketThread] Enter the listen server socket");
				serverSocket = mAdapter.listenUsingInsecureRfcommWithServiceRecord(NAME, CUSTOM_UUID);
				// serverSocket =
				// mAdapter.listenUsingRfcommWithServiceRecord(NAME,
				// CUSTOM_UUID);
				Log.v(TAG,
						"---->[ServerSocketThread] serverSocket hash code = " + serverSocket.hashCode());
				isServerSocketValid = true;

			} catch (IOException e) {
				Log.e(TAG, "---->[ServerSocketThread] Constructure: listen() failed", e);
				e.printStackTrace();
				notifyUiFromToast("Listen failed. Restart application again");
				isServerSocketValid = false;
				mServerSocketThread = null;
				// BluetoothConnService.this.startSession();
			}
			mmServerSocket = serverSocket;

			String serverSocketName = mmServerSocket.toString();
			Log.v(TAG, "---->[ServerSocketThread] serverSocket name = " + serverSocketName);
		}

		public void start() {
			this.thread.start();
		}

		@Override
		public void run() {
			if (D)
				Log.d(TAG, "---->BEGIN ServerSocketThread " + this);
			BluetoothSocket socket = null;

			while (isServerSocketValid) {
				try {
					Log.v(TAG, "---->[ServerSocketThread] Enter while loop");
					Log.v(TAG,
							"---->[ServerSocketThread] serverSocket hash code = "
									+ mmServerSocket.hashCode());
					socket = mmServerSocket.accept();

					Log.v(TAG, "---->[ServerSocketThread] Got client socket");
				} catch (IOException e) {
					Log.e(TAG, "---->accept() failed", e);
					break;
				}

				if (socket != null) {
					synchronized (BluetoothConnModel.this) {
						Log.v(TAG,
								"---->[ServerSocketThread] "
										+ socket.getRemoteDevice()
										+ " is connected.");
						connected(socket);
						/*
						 * if (mServerSocketThread != null) {
						 * mServerSocketThread = null; Log.w(TAG,
						 * "[ServerSocketThread] NULL mServerSocketThread"); }
						 */
						BluetoothConnModel.this.disconnectServerSocket();
						break;
					}
				}
			}
			Log.v(TAG, "---->[ServerSocketThread] break from while");
			BluetoothConnModel.this.startSession();
		}

		public void disconnect() {
			if (D)
				Log.d(TAG, "---->[ServerSocketThread] disconnect " + this);
			try {
				Log.v(TAG,
						"---->[ServerSocketThread] disconnect serverSocket name = "
								+ mmServerSocket.toString());
				mmServerSocket.close();
				Log.v(TAG,
						"---->[ServerSocketThread] mmServerSocket is closed.");
			} catch (IOException e) {
				Log.e(TAG, "---->close() of server failed", e);
			}
		}
	}

	/**
	 * Connecting as a client
	 */
	private class SocketThread implements Runnable {
		private BluetoothSocket mmSocket;
		private final BluetoothDevice mmDevice;
		private Thread thread = null;
		private BluetoothSocket tmp = null;

		// private final ExecutorService pool;
		@SuppressLint("NewApi")
		public SocketThread(BluetoothDevice device) {
			this.thread = new Thread(this);
			Log.v(TAG, "---->[SocketThread] Enter these server sockets");
//			BluetoothSocket tmp = null;
			mmDevice = device;

			// Get a BluetoothSocket for a connection with the given
			// BluetoothDevice

			try {
				// The UUID passed here must match the UUID used by the server
				// device when it opened its BluetoothServerSocket.
				// 客户端用的
//				int sdk = Integer.parseInt(Build.VERSION.SDK);
//				if(sdk >= 10){
					tmp = device.createInsecureRfcommSocketToServiceRecord(CUSTOM_UUID);
//					tmp = device.createRfcommSocketToServiceRecord(CUSTOM_UUID);
					Log.v(TAG, "默认UUID:" + CUSTOM_UUID.toString());
//				}else{
//					tmp = device.createRfcommSocketToServiceRecord(CUSTOM_UUID);
//				}

				Log.v(TAG,"---->[SocketThread] Constructure: Get a BluetoothSocket for a connection, create Rfcomm");
			} catch (Exception e) {
				Log.e(TAG, "---->create() failed", e);
			}
			mmSocket = tmp;
		}
		
		public void start() {
			this.thread.start();
		}

		@Override
		public void run() {
			if (D)
				Log.d(TAG, "---->BEGIN SocketThread" + this);
			// Cancel discovery because it will slow down the connection,
			// if you do want to check, call isDiscovering().
			mAdapter.cancelDiscovery();
			// Make a connection to the BluetoothSocket
			try {
				
				// This is a blocking call and will only return on a
				// successful connection or an exception
				/*
				 * issc2.1 Method createBondMethod =
				 * mmDevice.getClass().getMethod("createBond");
				 * createBondMethod.invoke(mmDevice);
				 */
				/**
				 * 当没有连接成功并且连接的次数小于5次时，重复进行连接 //可以考虑多发起几次连接
				 */
				// if (mmDevice.getBondState() == BluetoothDevice.BOND_NONE) {
				// boolean pindFlag = ClsUtils.setPin(mmDevice, "0000");
				// Log.v("-------->", "----pindFlag--->" + pindFlag);
				// boolean bondFlag = ClsUtils.createBond(mmDevice);
				// Log.v("-------->", "----bondFlag--->" + bondFlag);
				// }
				// Initiate the connection by calling connect().
				mmSocket.connect();
				Log.v(TAG, "---->[SocketThread] Return a successful connection");
			} catch (Exception e) {
				Log.e(TAG, "---->[SocketThread] Connection failed", e);
				e.printStackTrace();
				
				try {
					Log.v(TAG, "-----使用远程设备端UUID连接--->");
					
					ParcelUuid[] parcelUuid = mmDevice.getUuids();
					UUID uuid = parcelUuid[0].getUuid();
					Log.v(TAG, "远程设备端UUID:" + uuid.toString());
					mmSocket.close();
					mmSocket = mmDevice.createInsecureRfcommSocketToServiceRecord(uuid);
					mmSocket.connect();
				} catch (Exception e2) {
					e2.printStackTrace();
					
					Class<?> clazz = mmDevice.getClass();
					Class<?>[] paramTypes = new Class<?>[] { int.class };

					try {
						Log.v(TAG, "-----尝试反射连接--->");
						Method m = clazz.getMethod("createInsecureRfcommSocket", paramTypes);
						Object[] params = new Object[] { Integer.valueOf(1) };
						mmSocket.close();
						if(shouldUseFixChannel()){
							mmSocket = (BluetoothSocket) m.invoke(mmDevice, 6);
						}else{
							mmSocket = (BluetoothSocket) m.invoke(mmDevice, params);
						}
						mmSocket.connect();
					} catch (Exception e1) {
						Log.v(TAG, "-----反射失败--->" + e1.getMessage());
						
						try {
							Log.v(TAG, "-----尝试第二种反射连接--->");
							Method m2 = clazz.getMethod("createScoSocket");
							mmSocket.close();
							mmSocket = (BluetoothSocket) m2.invoke(mmDevice);
							mmSocket.connect();
							
						} catch (Exception e3) {
							Log.v(TAG, "-----反射2失败--->" + e3.getMessage());
							try {
								mmSocket.close();
								Log.v(TAG,"---->[SocketThread] Connect fail, close the client socket");
							} catch (IOException e21) {
								Log.e(TAG,"---->unable to close() socket during connection failure",e21);
							}
						}
						
					}
					
				}

//				this.thread = null;
				return;
			}
			
			// Reset the ConnectThread because we're done
			synchronized (BluetoothConnModel.this) {
				connected(mmSocket);
				Log.v(TAG, "---->[SocketThread] " + mmDevice + " is connected.");
			}
//			this.thread = null;
			if (D)
				Log.v(TAG, "---->END mConnectThread");
		}
	}
}
