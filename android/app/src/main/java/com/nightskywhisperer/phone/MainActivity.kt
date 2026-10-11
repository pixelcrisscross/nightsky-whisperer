package com.nightskywhisperer.phone

import android.Manifest
import android.app.Activity
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.media.AudioManager
import android.os.SystemClock
import android.content.Context
import android.content.pm.PackageManager
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.GeomagneticField
import android.hardware.SensorManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import okio.ByteString
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale
import java.util.concurrent.TimeUnit

class MainActivity : Activity(), SensorEventListener, LocationListener {
    private val mainHandler = Handler(Looper.getMainLooper())
    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()

    private lateinit var sensorManager: SensorManager
    private lateinit var locationManager: LocationManager
    private var rotationSensor: Sensor? = null
    private var websocket: WebSocket? = null
    private var connected = false
    private var lastLocation: Location? = null
    private var rotationVector: FloatArray? = null
    private var headingDeg: Double? = null
    private var pitchDeg: Double? = null
    private var rollDeg: Double? = null
    private var sensorAccuracy: Int = SensorManager.SENSOR_STATUS_UNRELIABLE
    private var lastSendAt = 0L
    @Volatile private var recordingAudio = false
    @Volatile private var audioRecord: AudioRecord? = null
    @Volatile private var audioTrack: AudioTrack? = null
    private var audioThread: Thread? = null
    private var audioButton: Button? = null
    private var playbackReleaseRunnable: Runnable? = null

    private lateinit var endpointInput: EditText
    private lateinit var connectionLabel: TextView
    private lateinit var sensorLabel: TextView
    private lateinit var logLabel: TextView

    private val telemetryRunnable = object : Runnable {
        override fun run() {
            if (connected) sendTelemetry()
            mainHandler.postDelayed(this, 200L) // 5 Hz is enough for the first sensor-link test.
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        sensorManager = getSystemService(Context.SENSOR_SERVICE) as SensorManager
        locationManager = getSystemService(Context.LOCATION_SERVICE) as LocationManager
        rotationSensor = sensorManager.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)
        buildUi()
        requestLocationPermissionIfNeeded()
        appendLog("Ready. Enter the UNO Q WebSocket URL and connect.")
        if (rotationSensor == null) appendLog("WARNING: TYPE_ROTATION_VECTOR not available on this phone.")
    }

    private fun buildUi() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 24, 24, 24)
        }
        val scroll = ScrollView(this)
        val content = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val title = TextView(this).apply {
            text = "NightSky Whisperer · Phone Bridge"
            textSize = 22f
        }
        endpointInput = EditText(this).apply {
            hint = "ws://UNO_Q_IP:8765/ws/phone"
            setSingleLine(true)
            setText("ws://192.168.43.100:8765/ws/phone")
        }
        val connectButton = Button(this).apply {
            text = "Connect to UNO Q"
            setOnClickListener { connectWebSocket() }
        }
        val disconnectButton = Button(this).apply {
            text = "Disconnect"
            setOnClickListener { disconnectWebSocket("Disconnected by user") }
        }
        val permissionButton = Button(this).apply {
            text = "Grant location permission"
            setOnClickListener { requestLocationPermissionIfNeeded(force = true) }
        }
        audioButton = Button(this).apply {
            text = "Record mic (up to 12s) and play back"
            setOnClickListener {
                if (recordingAudio) stopMicrophoneCapture() else startMicrophoneCapture()
            }
        }
        connectionLabel = TextView(this).apply { text = "Connection: not connected"; textSize = 16f }
        sensorLabel = TextView(this).apply { textSize = 15f; text = "Sensors: waiting…" }
        logLabel = TextView(this).apply { textSize = 13f; setTextIsSelectable(true) }
        content.addView(title)
        content.addView(TextView(this).apply { text = "UNO Q WebSocket URL"; textSize = 14f })
        content.addView(endpointInput)
        content.addView(connectButton)
        content.addView(disconnectButton)
        content.addView(permissionButton)
        content.addView(audioButton)
        content.addView(connectionLabel)
        content.addView(sensorLabel)
        content.addView(TextView(this).apply { text = "Event log"; textSize = 18f })
        content.addView(logLabel)
        scroll.addView(content)
        root.addView(scroll, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        setContentView(root)
    }

    private fun connectWebSocket() {
        val url = endpointInput.text.toString().trim()
        if (!url.startsWith("ws://") && !url.startsWith("wss://")) {
            appendLog("URL must begin with ws:// or wss://")
            return
        }
        disconnectWebSocket(null)
        connectionLabel.text = "Connection: connecting…"
        appendLog("Connecting to $url")
        val request = Request.Builder().url(url).build()
        websocket = httpClient.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                runOnUiThread {
                    connected = true
                    connectionLabel.text = "Connection: connected"
                    appendLog("WebSocket connected")
                    mainHandler.removeCallbacks(telemetryRunnable)
                    mainHandler.post(telemetryRunnable)
                }
            }

            
override fun onMessage(webSocket: WebSocket, text: String) {
    val json = try {
        JSONObject(text)
    } catch (e: Exception) {
        runOnUiThread { appendLog("Server: $text") }
        return
    }

    val type = json.optString("type")

    // IMPORTANT: initialize playback synchronously before the next
    // binary WebSocket message can be handled.
    when (type) {
        "audio_playback_start" -> {
            startPcmPlayback(
                json.optInt("sample_rate_hz", AUDIO_SAMPLE_RATE_HZ)
            )
            return
        }

        "audio_playback_end" -> {
            scheduleAudioPlaybackRelease()
            return
        }
    }

    // The other messages can continue to update the UI asynchronously.
    runOnUiThread {
        when (type) {
            "hello" ->
                appendLog("Server: ${json.optString("message")}")

            "ack" -> {
                if (json.has("telemetry_count")) {
                    appendLog(
                        "Server ACK: telemetry #${json.optInt("telemetry_count")}"
                    )
                } else {
                    appendLog("Server: ${json.optString("message")}")
                }
            }

            "audio_started" ->
                appendLog("Mic capture started; speak now (max 12 seconds).")

            "audio_saved" ->
                appendLog(
                    "UNO Q saved ${json.optInt("pcm_bytes")} PCM bytes " +
                    "(${json.optDouble("duration_seconds")} s) to " +
                    json.optString("path")
                )

            "error" ->
                appendLog("Server error: ${json.optString("message")}")

            else ->
                appendLog("Server: $text")
        }
    }
}


            override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                val track = audioTrack
                if (track == null) {
                    runOnUiThread { appendLog("Received audio bytes without an active playback track") }
                    return
                }
                try {
                    val data = bytes.toByteArray()
                    var offset = 0
                    while (offset < data.size) {
                        val written = track.write(data, offset, data.size - offset, AudioTrack.WRITE_BLOCKING)
                        if (written <= 0) throw IllegalStateException("AudioTrack write returned $written")
                        offset += written
                    }
                } catch (e: Exception) {
                    runOnUiThread { appendLog("Speaker playback error: ${e.message}") }
                }
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(code, reason)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                runOnUiThread {
                    connected = false
                    connectionLabel.text = "Connection: closed ($code)"
                    mainHandler.removeCallbacks(telemetryRunnable)
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                runOnUiThread {
                    connected = false
                    connectionLabel.text = "Connection: failed"
                    mainHandler.removeCallbacks(telemetryRunnable)
                    appendLog("Connection failed: ${t.message ?: t.javaClass.simpleName}")
                }
            }
        })
    }

    private fun disconnectWebSocket(logMessage: String?) {
        connected = false
        mainHandler.removeCallbacks(telemetryRunnable)
        websocket?.close(1000, "Client disconnect")
        websocket = null
        connectionLabel.text = "Connection: not connected"
        if (logMessage != null) appendLog(logMessage)
    }

    private fun requestLocationPermissionIfNeeded(force: Boolean = false) {
        val granted = checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
            checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
        if (!granted && (force || shouldShowRequestPermissionRationale(Manifest.permission.ACCESS_FINE_LOCATION) ||
                checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED)) {
            requestPermissions(
                arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION),
                LOCATION_REQUEST_CODE
            )
        } else if (granted) {
            startLocationUpdates()
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == LOCATION_REQUEST_CODE) {
            if (grantResults.any { it == PackageManager.PERMISSION_GRANTED }) {
                appendLog("Location permission granted")
                startLocationUpdates()
            } else appendLog("Location permission denied; telemetry will send null coordinates")
        } else if (requestCode == AUDIO_REQUEST_CODE) {
            if (grantResults.any { it == PackageManager.PERMISSION_GRANTED }) {
                appendLog("Microphone permission granted. Tap the audio button to start a loopback test.")
            } else appendLog("Microphone permission denied; audio test unavailable")
        }
    }

    private fun startLocationUpdates() {
        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED &&
            checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) != PackageManager.PERMISSION_GRANTED) return
        try {
            for (provider in locationManager.getProviders(true)) {
                if (provider == LocationManager.GPS_PROVIDER || provider == LocationManager.NETWORK_PROVIDER) {
                    try { locationManager.requestLocationUpdates(provider, 1000L, 0f, this, Looper.getMainLooper()) }
                    catch (e: Exception) { appendLog("Location provider $provider: ${e.message}") }
                    try {
                        val old = locationManager.getLastKnownLocation(provider)
                        if (old != null && (lastLocation == null || old.time > lastLocation!!.time)) lastLocation = old
                    } catch (_: SecurityException) { }
                }
            }
        } catch (e: SecurityException) {
            appendLog("Location permission error: ${e.message}")
        }
        updateSensorLabel()
    }

    override fun onLocationChanged(location: Location) {
        if (lastLocation == null || location.time >= lastLocation!!.time) lastLocation = location
        updateSensorLabel()
    }

    override fun onSensorChanged(event: SensorEvent) {
        if (event.sensor.type != Sensor.TYPE_ROTATION_VECTOR) return
        rotationVector = event.values.copyOf()
        sensorAccuracy = event.accuracy
        val matrix = FloatArray(9)
        val angles = FloatArray(3)
        SensorManager.getRotationMatrixFromVector(matrix, event.values)
        SensorManager.getOrientation(matrix, angles)
        headingDeg = ((Math.toDegrees(angles[0].toDouble()) % 360.0) + 360.0) % 360.0
        pitchDeg = Math.toDegrees(angles[1].toDouble())
        rollDeg = Math.toDegrees(angles[2].toDouble())
        updateSensorLabel()
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {
        sensorAccuracy = accuracy
    }

    private fun updateSensorLabel() {
        val loc = lastLocation
        val h = headingDeg?.let { String.format(Locale.US, "%.1f°", it) } ?: "—"
        val p = pitchDeg?.let { String.format(Locale.US, "%.1f°", it) } ?: "—"
        val r = rollDeg?.let { String.format(Locale.US, "%.1f°", it) } ?: "—"
        val gps = if (loc != null) String.format(Locale.US, "%.5f, %.5f (±%.0fm)", loc.latitude, loc.longitude, loc.accuracy) else "waiting for location"
        sensorLabel.text = "Phone top-edge heading: $h\nPitch: $p   Roll: $r\nLocation: $gps\nRotation sensor accuracy code: $sensorAccuracy"
    }

    private fun sendTelemetry() {
        val socket = websocket ?: return
        val now = System.currentTimeMillis()
        if (now - lastSendAt < 180L) return
        lastSendAt = now
        val loc = lastLocation
        val locationJson = JSONObject()
            .put("latitude_deg", loc?.latitude ?: JSONObject.NULL)
            .put("longitude_deg", loc?.longitude ?: JSONObject.NULL)
            .put("altitude_m", if (loc != null && loc.hasAltitude()) loc.altitude else JSONObject.NULL)
            .put("accuracy_m", loc?.accuracy ?: JSONObject.NULL)
            .put("provider", loc?.provider ?: JSONObject.NULL)
            .put("location_time_ms", loc?.time ?: JSONObject.NULL)

        val vectorJson = JSONArray()
        rotationVector?.forEach { vectorJson.put(it.toDouble()) }
        val declination = if (loc != null) {
            try {
                GeomagneticField(
                    loc.latitude.toFloat(),
                    loc.longitude.toFloat(),
                    (if (loc.hasAltitude()) loc.altitude else 0.0).toFloat(),
                    now
                ).declination.toDouble()
            } catch (_: Exception) { null }
        } else null

        val orientationJson = JSONObject()
            .put("sensor", "TYPE_ROTATION_VECTOR")
            .put("rotation_vector", vectorJson)
            .put("phone_top_azimuth_deg", headingDeg ?: JSONObject.NULL)
            .put("pitch_deg", pitchDeg ?: JSONObject.NULL)
            .put("roll_deg", rollDeg ?: JSONObject.NULL)
            .put("magnetic_declination_deg", declination ?: JSONObject.NULL)
            .put("accuracy_code", sensorAccuracy)

        val packet = JSONObject()
            .put("type", "telemetry")
            .put("protocol_version", 1)
            .put("device_id", "android-phone")
            .put("ts_unix_ms", now)
            .put("location", locationJson)
            .put("orientation", orientationJson)
        if (!socket.send(packet.toString())) appendLog("WebSocket send queue rejected telemetry")
    }

    private fun startMicrophoneCapture() {
        if (!connected || websocket == null) {
            appendLog("Connect to the UNO Q before starting the audio test")
            return
        }
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), AUDIO_REQUEST_CODE)
            return
        }
        val minBytes = AudioRecord.getMinBufferSize(
            AUDIO_SAMPLE_RATE_HZ, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT
        )
        if (minBytes <= 0) {
            appendLog("This phone could not configure 16 kHz mono microphone capture (code $minBytes)")
            return
        }
        val bufferBytes = maxOf(minBytes * 2, 8192)
        val recorder = try {
            AudioRecord.Builder()
                .setAudioSource(MediaRecorder.AudioSource.VOICE_RECOGNITION)
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setSampleRate(AUDIO_SAMPLE_RATE_HZ)
                        .setChannelMask(AudioFormat.CHANNEL_IN_MONO)
                        .build()
                )
                .setBufferSizeInBytes(bufferBytes)
                .build()
        } catch (e: Exception) {
            appendLog("Could not initialize microphone: ${e.message}")
            return
        }
        if (recorder.state != AudioRecord.STATE_INITIALIZED) {
            recorder.release()
            appendLog("AudioRecord did not initialize")
            return
        }
        val socket = websocket ?: run { recorder.release(); return }
        val startMessage = JSONObject()
            .put("type", "audio_start")
            .put("sample_rate_hz", AUDIO_SAMPLE_RATE_HZ)
            .put("channels", 1)
            .put("encoding", "pcm_s16le")
            .put("max_seconds", AUDIO_MAX_SECONDS)
        if (!socket.send(startMessage.toString())) {
            recorder.release()
            appendLog("Could not queue audio_start on WebSocket")
            return
        }
        recordingAudio = true
        audioRecord = recorder
        audioButton?.text = "Stop recording and play it back"
        try {
            recorder.startRecording()
        } catch (e: Exception) {
            recordingAudio = false
            audioRecord = null
            recorder.release()
            socket.send(JSONObject().put("type", "audio_stop").toString())
            audioButton?.text = "Record mic (up to 12s) and play back"
            appendLog("Could not start microphone: ${e.message}")
            return
        }
        audioThread = Thread({
            val buffer = ByteArray(4096)
            var totalBytes = 0
            val startedAt = SystemClock.elapsedRealtime()
            try {
                while (recordingAudio) {
                    if (SystemClock.elapsedRealtime() - startedAt >= AUDIO_MAX_DURATION_MS) {
                        recordingAudio = false
                        break
                    }
                    val count = recorder.read(buffer, 0, buffer.size, AudioRecord.READ_BLOCKING)
                    if (count > 0 && recordingAudio) {
                        val frame = ByteString.of(*buffer.copyOf(count))
                        if (!socket.send(frame)) {
                            runOnUiThread { appendLog("WebSocket rejected microphone audio chunk") }
                            recordingAudio = false
                            break
                        }
                        totalBytes += count
                    } else if (count < 0) {
                        runOnUiThread { appendLog("Microphone read error: $count") }
                        recordingAudio = false
                        break
                    }
                }
            } catch (e: Exception) {
                runOnUiThread { appendLog("Microphone capture error: ${e.message}") }
            } finally {
                try { if (recorder.recordingState == AudioRecord.RECORDSTATE_RECORDING) recorder.stop() } catch (_: Exception) { }
                try { recorder.release() } catch (_: Exception) { }
                audioRecord = null
                recordingAudio = false
                socket.send(JSONObject().put("type", "audio_stop").put("pcm_bytes_sent", totalBytes).toString())
                runOnUiThread {
                    audioButton?.text = "Record mic (up to 12s) and play back"
                    appendLog("Microphone capture ended; waiting for UNO Q loopback")
                }
            }
        }, "nightsky-mic-capture")
        audioThread?.start()
        appendLog("Recording started. Speak a short phrase, then tap stop; the UNO Q will echo it to the phone speaker.")
    }

    private fun stopMicrophoneCapture() {
        if (!recordingAudio) return
        recordingAudio = false
        try { audioRecord?.stop() } catch (_: Exception) { }
        audioButton?.text = "Finishing recording…"
    }

    private fun startPcmPlayback(sampleRate: Int) {
        releaseAudioPlayback()
        val safeRate = if (sampleRate > 0) sampleRate else AUDIO_SAMPLE_RATE_HZ
        val minBytes = AudioTrack.getMinBufferSize(
            safeRate, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT
        )
        if (minBytes <= 0) {
            appendLog("Could not initialize speaker playback (code $minBytes)")
            return
        }
        try {
            val track = AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setSampleRate(safeRate)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .build()
                )
                .setBufferSizeInBytes(maxOf(minBytes * 2, 8192))
                .setTransferMode(AudioTrack.MODE_STREAM)
                .build()
            if (track.state != AudioTrack.STATE_INITIALIZED) {
                track.release()
                appendLog("AudioTrack did not initialize")
                return
            }
            audioTrack = track
            track.play()
            appendLog("Playing returned microphone audio through phone speaker")
        } catch (e: Exception) {
            audioTrack = null
            appendLog("Could not start speaker playback: ${e.message}")
        }
    }

    private fun scheduleAudioPlaybackRelease() {
        playbackReleaseRunnable?.let { mainHandler.removeCallbacks(it) }
        val release = Runnable { releaseAudioPlayback() }
        playbackReleaseRunnable = release
        mainHandler.postDelayed(release, 650L)
    }

    private fun releaseAudioPlayback() {
        playbackReleaseRunnable?.let { mainHandler.removeCallbacks(it) }
        playbackReleaseRunnable = null
        val track = audioTrack
        audioTrack = null
        try { track?.pause() } catch (_: Exception) { }
        try { track?.flush() } catch (_: Exception) { }
        try { track?.release() } catch (_: Exception) { }
    }

    private fun appendLog(message: String) {
        if (!::logLabel.isInitialized) return
        val old = logLabel.text.toString().lines().takeLast(16)
        logLabel.text = (old + "• $message").joinToString("\n")
    }

    override fun onResume() {
        super.onResume()
        rotationSensor?.let { sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME) }
        startLocationUpdates()
    }

    override fun onPause() {
        sensorManager.unregisterListener(this)
        try { locationManager.removeUpdates(this) } catch (_: SecurityException) { }
        super.onPause()
    }

    override fun onDestroy() {
        stopMicrophoneCapture()
        releaseAudioPlayback()
        disconnectWebSocket(null)
        httpClient.dispatcher.executorService.shutdown()
        super.onDestroy()
    }

    companion object {
        private const val LOCATION_REQUEST_CODE = 7301
        private const val AUDIO_REQUEST_CODE = 7302
        private const val AUDIO_SAMPLE_RATE_HZ = 16000
        private const val AUDIO_MAX_SECONDS = 12
        private const val AUDIO_MAX_DURATION_MS = AUDIO_MAX_SECONDS * 1000L
    }
}
