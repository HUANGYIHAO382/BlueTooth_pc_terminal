package com.iknet.bloodmeasuredemo;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.DialogInterface;
import android.content.Intent;
import android.os.Bundle;
import android.text.TextUtils;
import android.util.Log;
import android.view.View;
import android.view.View.OnClickListener;
import android.widget.Button;
import android.widget.Toast;

import com.iknet.ble.common.BluetoothDeviceManager;
import com.iknet.iknetbluetoothlibrary.BluetoothManager;
import com.iknet.utils.mytools;
import com.vise.baseble.ViseBle;

import java.math.BigInteger;
import java.util.LinkedList;
import java.util.Queue;

import jluzh.scanner.ComBean;
import jluzh.scanner.OnDataReceivedLisener;
import jluzh.scanner.SerialControl;

public class MainActivity extends Activity{

	private static final String TAG = MainActivity.class.getSimpleName();
	private Button btn_startMeasure,btnBlood;
	
	@Override
	protected void onCreate(Bundle savedInstanceState) {
		// TODO Auto-generated method stub
		super.onCreate(savedInstanceState);
		setContentView(R.layout.activity_main);
		initView();



//		DispQueue = new DispQueueThread();
//		DispQueue.start();
//
//		//创建串口对象
//		scanner = new SerialControl("/dev/ttyS2", "9600", new OnDataReceivedLisener() {
//			@Override
//			public void onDataReceived(ComBean data) {
//				//数据接收量大或接收时弹出软键盘，界面会卡顿,可能和6410的显示性能有关
//				//直接刷新显示，接收数据量大时，卡顿明显，但接收与显示同步。
//				//用线程定时刷新显示可以获得较流畅的显示效果，但是接收数据速度快于显示速度时，显示会滞后。
//				//最终效果差不多-_-，线程定时刷新稍好一些。
//				DispQueue.AddQueue(data);//线程定时刷新显示(推荐)
//
////                TTS2DispRecData(data);
//			}
//		});
//		//  scanner.powerOn();   // 上电管理，专用平台有效
//		scanner.connect();
////		byte[] cmd = new byte[]{(byte) 0xCC, (byte) 0x80, (byte) 0x03, (byte) 0x03, (byte) 0x01, (byte) 0x02, (byte) 0x00, (byte) 0x03};//开始测量
//		scanner.send("61$".getBytes());


	}


	private void initView() {
		btn_startMeasure = (Button) findViewById(R.id.btn_startMeasure);
		btn_startMeasure.setOnClickListener(new OnClickListener() {

			@Override
			public void onClick(View v) {
				Intent intent = new Intent(MainActivity.this, BluetoothConnMeasureActivity.class);
				startActivity(intent);
			}
		});

//		btnBlood = (Button) findViewById(R.id.btn_startblood);
//		btnBlood.setOnClickListener(new OnClickListener() {
//			@Override
//			public void onClick(View v) {
//				byte[] cmd = new byte[]{(byte) 0xCC, (byte) 0x80, (byte) 0x03, (byte) 0x03, (byte) 0x01, (byte) 0x02, (byte) 0x00, (byte) 0x03};//开始测量
//				scanner.send(cmd);
//			}
//		});
	}


}
