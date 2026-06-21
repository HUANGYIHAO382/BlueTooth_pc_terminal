package com.iknet.bloodmeasuredemo;

import com.iknet.ble.common.BluetoothDeviceManager;

public class BaseApp extends android.app.Application {

    @Override
    public void onCreate() {
        super.onCreate();
        BluetoothDeviceManager.getInstance().init(this);
    }
}
