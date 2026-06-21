package com.iknet.bloodmeasuredemo;

import java.math.BigInteger;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.ParcelUuid;
import android.provider.Settings;
import android.text.TextUtils;
import android.util.Log;
import android.view.KeyEvent;
import android.view.View;
import android.view.View.OnClickListener;
import android.view.animation.Animation;
import android.view.animation.AnimationUtils;
import android.view.animation.LinearInterpolator;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;

import com.iknet.ble.common.BluetoothDeviceManager;
import com.iknet.ble.common.ToastUtil;
import com.iknet.ble.event.CallbackDataEvent;
import com.iknet.ble.event.ConnectEvent;
import com.iknet.ble.event.NotifyDataEvent;
import com.iknet.iknetbluetoothlibrary.BluetoothManager;
import com.iknet.iknetbluetoothlibrary.BluetoothManager.OnBTMeasureListener;
import com.iknet.iknetbluetoothlibrary.MeasurementResult;
import com.iknet.iknetbluetoothlibrary.util.PermissionUtil;
import com.iknet.utils.mytools;
import com.tbruyelle.rxpermissions2.RxPermissions;
import com.vise.baseble.ViseBle;
import com.vise.baseble.callback.scan.IScanCallback;
import com.vise.baseble.common.PropertyType;
import com.vise.baseble.model.BluetoothLeDevice;
import com.vise.baseble.model.BluetoothLeDeviceStore;
import com.vise.xsnow.event.BusManager;
import com.vise.xsnow.event.Subscribe;

import io.reactivex.functions.Consumer;
import no.nordicsemi.android.support.v18.scanner.BluetoothLeScannerCompat;
import no.nordicsemi.android.support.v18.scanner.ScanCallback;
import no.nordicsemi.android.support.v18.scanner.ScanFilter;
import no.nordicsemi.android.support.v18.scanner.ScanResult;
import no.nordicsemi.android.support.v18.scanner.ScanSettings;

/**
 * 蓝牙连接与测量
 */
public class BluetoothConnMeasureActivity extends Activity implements OnClickListener, BluetoothDeviceManager.OnBleDataListener {
    private static final String TAG = "BluetoothConnActivity";
    public final static UUID BP_SERVICE_UUID = UUID.fromString("00001810-0000-1000-8000-00805f9b34fb");


    public static final String CONNECT_ORDER = "cc80020301010001";
    public static final String POWER_ORDER = "cc80020304040001";
    public static final String START_MEASURE = "cc80020301020002";
    public static final String STOP_ORDER = "cc80020301030003";
    private View imgAnim;
    private BluetoothAdapter _bluetooth = BluetoothAdapter.getDefaultAdapter();
    private TextView tv_connect_state, tv_turgoscope_power, tv_heart;
    private Button btn_stop_measure;
    private Animation operatingAnim;
    private BluetoothManager bluetoothManager;
    private TextView electricStatusTV, mHeart, mTvStatus;
    private boolean isBLE = false;

    public static final UUID UUID_SERVICE = UUID.fromString("0000fff0-0000-1000-8000-00805f9b34fb");
    public static final UUID UUID_NOTIFY = UUID.fromString("0000fff1-0000-1000-8000-00805f9b34fb");
    public static final UUID UUID_WRITE = UUID.fromString("0000fff2-0000-1000-8000-00805f9b34fb");

    public List<BluetoothDevice> mDevice = new ArrayList<>();

    private final Handler mHandler = new Handler();

    public BluetoothLeDevice mConnectDevice;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.bluetooth);
        initView();
        initData();
        setBluetooth();
        electricStatusTV = findViewById(R.id.tv_turgoscope_power);
        mTvStatus = findViewById(R.id.tv_connect_state);
        mHeart = findViewById(R.id.tv_heart);
        BusManager.getBus().register(this);
        BluetoothDeviceManager.getInstance().setOnBleDataListener(this);
    }

    public void showToast(String msg) {
        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show();
    }

    private void getResult(String bloodData) {
//		bean.setHighpressure(Integer.valueOf(mytools.deal16to10(bloodData.substring(28, 30)))); //收缩压
//		bean.setLowvoltage(Integer.valueOf(mytools.deal16to10(bloodData.substring(32, 34))));   //舒张压
//		bean.setPulse(Integer.valueOf(mytools.deal16to10(bloodData.substring(36, 38))));        //脉搏

        String hightPress = mytools.deal16to10(bloodData.substring(28, 30));
        String lowPress = mytools.deal16to10(bloodData.substring(32, 34));
        String pulse = mytools.deal16to10(bloodData.substring(36, 38));
        Bundle bundle = new Bundle();
        bundle.putString("high", hightPress);
        bundle.putString("low", lowPress);
        bundle.putString("pulse", pulse);
        Intent intent = new Intent(this, MeasurementResultActivity.class);
        intent.putExtras(bundle);
        startActivity(intent);
        finish();
    }

    @Override
    protected void onDestroy() {
        // TODO Auto-generated method stub
        super.onDestroy();
        mHandler.removeCallbacks(null);

        if (bluetoothManager != null) {
            bluetoothManager.stopBTAffair();
        }

        if (mConnectDevice != null) {
            if (BluetoothDeviceManager.getInstance().isConnected(mConnectDevice)) {
                BluetoothDeviceManager.getInstance().disconnect(mConnectDevice);
            }
        }

        BusManager.getBus().unregister(this);

//		stopService(new Intent(getApplicationContext(), BluetoothService.class));
    }

    public void initView() {
        imgAnim = findViewById(R.id.imgAnim);
        tv_connect_state = (TextView) findViewById(R.id.tv_connect_state);
        tv_turgoscope_power = (TextView) findViewById(R.id.tv_turgoscope_power);
        tv_heart = (TextView) findViewById(R.id.tv_heart);
        btn_stop_measure = (Button) findViewById(R.id.btn_stop_measure);

        btn_stop_measure.setOnClickListener(this);
    }

    private void initData() {
        bluetoothManager = BluetoothManager.getInstance(this);
    }

    /**
     * 设置蓝牙信息 ：如果蓝牙可用，则打开蓝牙； 如果蓝牙不可用，则进行提示
     */
    private void setBluetooth() {

        if (_bluetooth == null) {
            Toast.makeText(this, "本机没有找到蓝牙硬件或驱动！", Toast.LENGTH_LONG).show();
            finish();
            return;
        }

        if (!_bluetooth.isEnabled()) {
            //提醒用户打开蓝牙
            Intent enableBtIntent = new Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE);
            startActivityForResult(enableBtIntent, 1);
        } else {
            requestLocPermission();
        }

    }

    private void requestLocPermission() {
        new RxPermissions(this).request(Manifest.permission.ACCESS_COARSE_LOCATION)
                .subscribe(new Consumer<Boolean>() {
                    @Override
                    public void accept(Boolean granted) throws Exception {
                        if (granted) {
                            // 蓝牙已经打开，开始搜索、连接和测量
                            startAnim();
                            startScan();
                        } else {
                            Intent intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS);
                            intent.setData(Uri.parse("package:" + getPackageName()));
                            startActivityForResult(intent, REQUEST_CODE_PERMISSION_SETTING);
                        }
                    }
                });
    }

    /**
     * 开始扫描
     */
    private void startScan() {
        Log.d(TAG, "startScan");
        ViseBle.getInstance().startScan(periodScanCallback);
    }

    /**
     * 停止扫描
     */
    private void stopScan() {
        ViseBle.getInstance().stopScan(periodScanCallback);
    }

    /**
     * 扫描回调
     */
    private com.vise.baseble.callback.scan.ScanCallback periodScanCallback = new com.vise.baseble.callback.scan.ScanCallback(new IScanCallback() {
        @Override
        public void onDeviceFound(final BluetoothLeDevice bluetoothLeDevice) {
            String deviceName = bluetoothLeDevice.getName();
            if (!TextUtils.isEmpty(deviceName)) {
                Log.e(TAG, "Founded Scan Device:" + bluetoothLeDevice.getName());
                if (deviceName.contains("RBP") || deviceName.contains("BP")) {
                    if (deviceName.contains("A")) {
                        stopScan();
                        isBLE = true;
                        mConnectDevice = bluetoothLeDevice;
                        if (!BluetoothDeviceManager.getInstance().isConnected(bluetoothLeDevice)) {
                            BluetoothDeviceManager.getInstance().connect(bluetoothLeDevice);
                        }
                    }
                }
            }

        }

        @Override
        public void onScanFinish(BluetoothLeDeviceStore bluetoothLeDeviceStore) {
            Log.d(TAG, "scan finish " + bluetoothLeDeviceStore);
//            bluetoothManager.startBTAffair(onBTMeasureListener);
        }

        @Override
        public void onScanTimeout() {
            Log.d(TAG, "scan timeout");
            bluetoothManager.startBTAffair(onBTMeasureListener);
        }

    });

    private no.nordicsemi.android.support.v18.scanner.ScanCallback scanCallback = new ScanCallback() {
        @Override
        public void onScanResult(final int callbackType, final ScanResult result) {
            // do nothing
        }

        @Override
        public void onBatchScanResults(final List<ScanResult> results) {
            Log.d(TAG, results.size() + "");
            if (results != null) {
                int size = results.size();
                if (size > 0) {
                    stopScan();
                    List<ScanResult> list = results;
                    for (int i = 0; i < list.size(); i++) {
                        ScanResult result = list.get(i);
                        final BluetoothDevice device = result.getDevice();
                        String deviceName = device.getName();

                        if (TextUtils.isEmpty(deviceName)) {
                            return;
                        }
                        Log.d(TAG, deviceName);
                        if (deviceName.contains("RBP") || deviceName.contains("BP")) {
                            if (deviceName.contains("A")) {

                            }
                        }
                    }
                }
            }
        }

        @Override
        public void onScanFailed(final int errorCode) {
            // should never be called
        }
    };

    /**
     * sdk会自动申请权限，如果失败则手动申请
     */
    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        // TODO Auto-generated method stub
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        switch (requestCode) {
            case BluetoothManager.REQUEST_FINE_LOCATION:
                //23以上版本蓝牙扫描需要定位权限(android.permission.ACCESS_COARSE_LOCATION)，此处判断是否获取成功
                if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                    // 获取权限成功
                    bluetoothManager.searchBluetooth();
                } else {
                    // 获取权限失败
                    Toast.makeText(BluetoothConnMeasureActivity.this, "权限获取失败", Toast.LENGTH_SHORT).show();
                    setPermissionApplyDialog();
                }
                break;

        }
    }

    @Override
    protected void onActivityResult(int arg0, int arg1, Intent intent) {
        super.onActivityResult(arg0, arg1, intent);
        if (arg0 == 1) {
            if (arg1 == Activity.RESULT_OK) {
//                startAnim();
//                //蓝牙打开成功，开始搜索、连接和测量
//                bluetoothManager.startBTAffair(onBTMeasureListener);
                requestLocPermission();
            } else {
                //蓝牙不能正常打开
                finish();
            }
        } else if (arg0 == REQUEST_CODE_PERMISSION_SETTING) {
            if (PermissionUtil.checkLocationPermission(this)) {
                bluetoothManager.searchBluetooth();
            } else {
                Toast.makeText(BluetoothConnMeasureActivity.this, "权限获取失败", Toast.LENGTH_SHORT).show();
                finish();
            }
        }
    }

    /**
     * 权限申请
     */
    private void setPermissionApplyDialog() {
        try {
            new AlertDialog.Builder(this)
                    .setTitle("提示")
                    .setMessage("蓝牙扫描需要定位权限。\n请点击“设置”-“权限管理”-“定位”打开所需权限。")
                    .setCancelable(false)
                    .setNegativeButton("拒绝",
                            new DialogInterface.OnClickListener() {
                                @Override
                                public void onClick(DialogInterface dialog, int which) {
                                    dialog.dismiss();
                                    BluetoothConnMeasureActivity.this.finish();
                                }
                            })
                    .setPositiveButton("设置",
                            new DialogInterface.OnClickListener() {

                                @Override
                                public void onClick(DialogInterface dialog, int which) {
                                    dialog.dismiss();
                                    startAppSettings();
                                }
                            }).show();
        } catch (Exception e) {
            e.printStackTrace();
        }

    }

    private static final int REQUEST_CODE_PERMISSION_SETTING = 102;

    /**
     * 启动应用的设置
     */
    private void startAppSettings() {
        Intent intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS);
        intent.setData(Uri.parse("package:" + getPackageName()));
        startActivityForResult(intent, REQUEST_CODE_PERMISSION_SETTING);
    }

    private OnBTMeasureListener onBTMeasureListener = new OnBTMeasureListener() {

        @Override
        public void onRunning(String running) {
            //测量过程中的压力值
            tv_heart.setText(running);
        }

        @Override
        public void onPower(String power) {
            //测量前获取的电量值
            setPower(power);
        }

        @Override
        public void onMeasureResult(MeasurementResult result) {
            //测量结果
            Bundle bundle = new Bundle();
            Intent intent = new Intent(BluetoothConnMeasureActivity.this, MeasurementResultActivity.class);
            intent.putExtra("measure_result", result);
            bundle.putString("high", result.getCheckShrink() + "");
            bundle.putString("low", result.getCheckDiastole() + "");
            bundle.putString("pulse", result.getCheckHeartRate() + "");
            intent.putExtras(bundle);
            startActivity(intent);
            finish();
        }

        @Override
        public void onMeasureError() {
            //测量错误
            Toast.makeText(BluetoothConnMeasureActivity.this,
                    "测量失败", Toast.LENGTH_SHORT).show();
            btn_stop_measure.setText(getResources().getString(R.string.re_test));
            stopAnim();
        }

        @Override
        public void onFoundFinish(List<BluetoothDevice> deviceList) {
            //搜索结束，deviceList.size()如果为0，则没有搜索到设备
            if (deviceList.size() == 0) {
                Toast.makeText(BluetoothConnMeasureActivity.this, "未搜索到设备", Toast.LENGTH_SHORT).show();
                finish();
            }
        }

        @Override
        public void onDisconnected(BluetoothDevice device) {
            //断开连接
            stopAnim();
            tv_heart.setText("0");
            tv_connect_state.setText(getResources().getString(R.string.not_connect_bluetooth));
            tv_turgoscope_power.setText("0");
            btn_stop_measure.setEnabled(true);
            btn_stop_measure.setText(getResources().getString(R.string.re_test));
        }

        @Override
        public void onConnected(boolean isConnected, BluetoothDevice device) {
            //是否连接成功
            if (isConnected) {
                Toast.makeText(BluetoothConnMeasureActivity.this,
                        device.getName() + getResources().getString(R.string.was_connected), Toast.LENGTH_SHORT).show();
                btn_stop_measure.setText(getResources().getString(R.string.stop_measurement));
                btn_stop_measure.setEnabled(true);
                tv_connect_state.setText(getResources().getString(R.string.connect_bluetooth));
            } else {
                stopAnim();
                Toast.makeText(BluetoothConnMeasureActivity.this,
                        getResources().getString(R.string.unable_to_connect_device) + device.getName(), Toast.LENGTH_SHORT).show();
            }
        }
    };

    // 开始播放蓝牙搜索动画
    public void startAnim() {
        operatingAnim = AnimationUtils.loadAnimation(this, R.anim.tip);
        LinearInterpolator lin = new LinearInterpolator();
        operatingAnim.setInterpolator(lin);
        imgAnim.startAnimation(operatingAnim);
        if (_bluetooth.isEnabled() == false) {
            imgAnim.clearAnimation();
        }
    }

    public void stopAnim() {
        imgAnim.clearAnimation();
    }

    @Override
    public void onClick(View v) {
        if(v.getId() == R.id.btn_stop_measure){
            if (isBLE) {
                if ("停止测量".equals(btn_stop_measure.getText())) {
                    stopAnim();
                    sendOrder(STOP_ORDER);
                    btn_stop_measure.setText("开始测量");

                } else if ("开始测量".equals(btn_stop_measure.getText())) {
                    tv_turgoscope_power.setText("0");
                    startAnim();
                    btn_stop_measure.setText("停止测量");
                    sendOrder(CONNECT_ORDER);
                }

            } else {
                dealStopMeasureBtn();
            }
        }
    }

    private void dealStopMeasureBtn() {
        if (btn_stop_measure.getText().toString().equals(getResources().getString(R.string.stop_measurement))) {
            tv_heart.setText("0");
            stopAnim();
            bluetoothManager.stopMeasure();
            btn_stop_measure.setText(getResources().getString(R.string.re_test));

        } else if (btn_stop_measure.getText().toString().equals(getResources().getString(R.string.re_test))) {
            tv_heart.setText("0");
            startAnim();
            btn_stop_measure.setText(getResources().getString(R.string.stop_measurement));
            if (bluetoothManager.isConnectBT()) {
                bluetoothManager.startMeasure();
            } else {
                bluetoothManager.startBTAffair(onBTMeasureListener);
            }

        }
    }


    private void setPower(String power) {
        if (Integer.valueOf(power) > 3600) {
            tv_turgoscope_power.setText("剩余电量：" + power);
        } else {
            stopAnim();
            tv_turgoscope_power.setText("血压计电量不足,请及时充电");
        }
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK) {
//			if (_bluetooth.isEnabled()) {
//				_bluetooth.disable();
//			}
            bluetoothManager.stopMeasure();
            finish();
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }


    @Subscribe
    public void showConnectedDevice(ConnectEvent event) {
        if (event != null) {
            if (event.isSuccess()) {
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        btn_stop_measure.setText("停止测量");
                        tv_connect_state.setText("已连接");
                        stopAnim();
                    }
                });
                BluetoothDeviceManager.getInstance().bindChannel(mConnectDevice, PropertyType.PROPERTY_WRITE, UUID_SERVICE, UUID_WRITE, null);
                BluetoothDeviceManager.getInstance().bindChannel(mConnectDevice, PropertyType.PROPERTY_NOTIFY, UUID_SERVICE, UUID_NOTIFY, null);
                BluetoothDeviceManager.getInstance().registerNotify(mConnectDevice, false);

                btn_stop_measure.postDelayed(new Runnable() {
                    @Override
                    public void run() {
                        sendOrder(CONNECT_ORDER);
                    }
                }, 1000);


            } else {
                if (event.isDisconnected()) {
                    tv_turgoscope_power.setText("0");
                    mTvStatus.setText("未连接蓝牙");
                    ToastUtil.showToast(BluetoothConnMeasureActivity.this, "Disconnect!");
                } else {
                    ToastUtil.showToast(BluetoothConnMeasureActivity.this, "Connect Failure!");
                    BluetoothDeviceManager.getInstance().connect(mConnectDevice);
                }
            }
        }
    }

    @Subscribe
    public void showDeviceCallbackData(CallbackDataEvent event) {
        if (event != null) {
            if (event.isSuccess()) {
                if (event.getBluetoothGattChannel() != null && event.getBluetoothGattChannel().getCharacteristic() != null
                        && event.getBluetoothGattChannel().getPropertyType() == PropertyType.PROPERTY_READ) {
                }
            } else {

            }
        }
    }

    public void sendOrder(String order) {
        BluetoothDeviceManager.getInstance().write(mConnectDevice, com.vise.baseble.utils.HexUtil.decodeHex(order.toCharArray()));
    }

    @Subscribe
    public void showDeviceNotifyData(NotifyDataEvent event) {
        if (event != null && event.getData() != null && event.getBluetoothLeDevice() != null
                && event.getBluetoothLeDevice().getAddress().equals(mConnectDevice.getAddress())) {
        }
    }

    @Override
    public void onBleData(final String data) {
        Log.d(TAG, data);
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                if (TextUtils.equals(data, "aa80020301010001")) {
                    sendOrder(POWER_ORDER);
                } else if (data.contains("aa80020404")) {
                    BigInteger batteryLevel = new BigInteger(data.substring(12, 16), 16);
                    int battery = batteryLevel.intValue();
                    if (battery > BluetoothManager.MIN_POWER) {
                        sendOrder(START_MEASURE);
                        electricStatusTV.setText(batteryLevel + "");
                    } else {
                        electricStatusTV.setText("血压计电量不足,请及时充电");
                    }
                } else if (data.contains("aa80020f0106")) {
                    getResult(data);
                } else if (data.contains("aa8002080105")) {//实时压力值
                    String currentValue = mytools.deal16to10(data.substring(20, 22));
                    mHeart.setText(currentValue);
                } else if (data.contains("aa8002030107")) { //测量失败
                    showToast("测量错误");
                    finish();
                }
            }
        });

    }
}
