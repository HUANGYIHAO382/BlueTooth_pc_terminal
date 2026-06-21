package com.iknet.bloodmeasuredemo;

import com.iknet.iknetbluetoothlibrary.MeasurementResult;

import android.app.Activity;
import android.os.Bundle;
import android.widget.TextView;

/**
 * 显示测量结果
 * @author Administrator
 *
 */
public class MeasurementResultActivity extends Activity{
	
	private TextView tv_ssy, tv_szy, tv_xl;
	

	String high,low,pulse;
	
	@Override
	protected void onCreate(Bundle savedInstanceState) {
		// TODO Auto-generated method stub
		super.onCreate(savedInstanceState);
		setContentView(R.layout.activity_measure_result);
		
		initView();
	}

	private void initView() {
		tv_ssy = (TextView) findViewById(R.id.tv_ssy);
		tv_szy = (TextView) findViewById(R.id.tv_szy);
		tv_xl = (TextView) findViewById(R.id.tv_xl);

		Bundle bundle = getIntent().getExtras();
		if(bundle != null){
			high = bundle.getString("high");
			low = bundle.getString("low");
			pulse = bundle.getString("pulse");
		}
		
		tv_ssy.setText(getString(R.string.systolic_pressure_) + high);
		tv_szy.setText(getString(R.string.diastolic_pressure_) + low);
		tv_xl.setText(getString(R.string.pulse_) + pulse);
	}
	
}
