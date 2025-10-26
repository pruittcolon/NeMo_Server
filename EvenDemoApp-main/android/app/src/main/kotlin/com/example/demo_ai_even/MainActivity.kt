package com.example.demo_ai_even

import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.util.Log
import com.example.demo_ai_even.bluetooth.BleChannelHelper
import com.example.demo_ai_even.bluetooth.BleManager
import com.example.demo_ai_even.cpp.Cpp
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel

class MainActivity: FlutterActivity(), EventChannel.StreamHandler {

    companion object {
        fun sendAudioResultToFlutter(message: String) {
            BleChannelHelper.bleSpeechRecognize(message)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Cpp.init()
        BleManager.instance.initBluetooth(this)

        // Example of where you might want to start the service.
        // You would typically call this after a successful BLE connection.
        startBleService()
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        BleChannelHelper.initChannel(this, flutterEngine)
    }

    /// Interface - EventChannel.StreamHandler
    override fun onListen(arguments: Any?, events: EventChannel.EventSink?) {
        Log.i(this::class.simpleName,"EventChannel.StreamHandler - OnListen: arguments = $arguments ,events = $events")
        BleChannelHelper.addEventSink(arguments as String?, events)
    }

    /// Interface - EventChannel.StreamHandler
    override fun onCancel(arguments: Any?) {
        Log.i(this::class.simpleName,"EventChannel.StreamHandler - OnCancel: arguments = $arguments")
        BleChannelHelper.removeEventSink(arguments as String?)
    }

    /**
     * Starts the BleForegroundService to maintain a persistent BLE connection
     * and show a notification.
     */
    private fun startBleService() {
        val serviceIntent = Intent(this, BleForegroundService::class.java)

        // For Android 8.0 (API level 26) and higher, use startForegroundService()
        // to start a foreground service.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(serviceIntent)
        } else {
            startService(serviceIntent)
        }
    }
}
