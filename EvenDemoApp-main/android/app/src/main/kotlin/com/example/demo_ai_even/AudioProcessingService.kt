package com.example.demo_ai_even

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import java.io.DataOutputStream
import java.io.File
import java.io.FileInputStream
import java.io.RandomAccessFile
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Foreground service that records microphone audio as 16 kHz mono PCM and
 * rolls files every ~15 seconds, writing proper WAV headers, then uploads
 * each chunk to a server endpoint.
 */
class AudioProcessingService : Service() {

    companion object {
        private const val TAG = "AudioProcessingService"
        private const val CHANNEL_ID = "even_ai_chunk_uploader"
        private const val NOTIF_ID = 12

        private const val DEFAULT_UPLOAD_URL = "http://10.0.0.1:8000/command"
        const val EXTRA_UPLOAD_URL = "upload_url"

        private const val SAMPLE_RATE = 16_000
        private const val CHANNEL_CONFIG = AudioFormat.CHANNEL_IN_MONO
        private const val AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT

        private const val CHUNK_SECONDS = 15
        private const val BYTES_PER_SAMPLE = 2
        private const val CHANNEL_COUNT = 1
    }

    private val isRunning = AtomicBoolean(false)
    private var audioRecord: AudioRecord? = null
    private var uploadUrl: String = DEFAULT_UPLOAD_URL

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForegroundServiceWithNotif()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        uploadUrl = intent?.getStringExtra(EXTRA_UPLOAD_URL) ?: DEFAULT_UPLOAD_URL
        if (isRunning.compareAndSet(false, true)) {
            Thread { recordLoop() }.start()
        }
        return START_STICKY
    }

    override fun onDestroy() {
        isRunning.set(false)
        try { audioRecord?.stop() } catch (_: Throwable) {}
        audioRecord?.release()
        audioRecord = null
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    // ------------------------------------------------------------------------------------
    // Foreground plumbing
    // ------------------------------------------------------------------------------------
    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val chan = NotificationChannel(
                CHANNEL_ID,
                "EvenAI - Chunk Uploader",
                NotificationManager.IMPORTANCE_LOW
            )
            chan.setSound(null, null)
            val nm = getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(chan)
        }
    }

    private fun startForegroundServiceWithNotif() {
        val notif: Notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("EvenAI")
            .setContentText("Capturing audio for server transcription")
            .setSmallIcon(android.R.drawable.presence_audio_online)
            .setOngoing(true)
            .build()

        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(
                NOTIF_ID,
                notif,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
            )
        } else {
            startForeground(NOTIF_ID, notif)
        }
    }

    // ------------------------------------------------------------------------------------
    // Recording + chunking
    // ------------------------------------------------------------------------------------
    private fun recordLoop() {
        val minBuf = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL_CONFIG, AUDIO_FORMAT)
        val frameBufBytes = maxOf(minBuf, SAMPLE_RATE / 2)
        val frameBufShorts = frameBufBytes / BYTES_PER_SAMPLE
        val buf = ShortArray(frameBufShorts)

        audioRecord = AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION,
            SAMPLE_RATE,
            CHANNEL_CONFIG,
            AUDIO_FORMAT,
            frameBufBytes
        )

        if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
            Log.e(TAG, "AudioRecord init failed")
            MainActivity.sendAudioResultToFlutter("❌ Mic init failed")
            stopSelf()
            return
        }

        audioRecord!!.startRecording()
        Log.i(TAG, "Recording started; uploading to $uploadUrl")
        MainActivity.sendAudioResultToFlutter("🎤 Recording started...")

        val chunkSamplesTarget = SAMPLE_RATE * CHUNK_SECONDS
        var chunkSamplesWritten = 0

        var currentWavFile = createNewWavFile()
        var raf = RandomAccessFile(currentWavFile, "rw")
        writeWavHeader(raf, SAMPLE_RATE, CHANNEL_COUNT, BYTES_PER_SAMPLE)

        while (isRunning.get()) {
            val read = audioRecord!!.read(buf, 0, buf.size)
            if (read <= 0) continue

            val pcmBytes = ShortArrayToByteArray(buf, read)
            raf.write(pcmBytes)
            chunkSamplesWritten += read

            if (chunkSamplesWritten >= chunkSamplesTarget) {
                finalizeWavHeaderAndClose(raf, currentWavFile)
                val toUpload = currentWavFile
                Thread { safeUpload(toUpload) }.start()
                MainActivity.sendAudioResultToFlutter("📤 Uploaded chunk: ${toUpload.name}")

                currentWavFile = createNewWavFile()
                raf = RandomAccessFile(currentWavFile, "rw")
                writeWavHeader(raf, SAMPLE_RATE, CHANNEL_COUNT, BYTES_PER_SAMPLE)
                chunkSamplesWritten = 0
            }
        }

        try {
            finalizeWavHeaderAndClose(raf, currentWavFile)
            Thread { safeUpload(currentWavFile) }.start()
            MainActivity.sendAudioResultToFlutter("📤 Uploaded final chunk: ${currentWavFile.name}")
        } catch (_: Throwable) {}

        try { audioRecord?.stop() } catch (_: Throwable) {}
        audioRecord?.release()
        audioRecord = null
        Log.i(TAG, "Recording stopped")
        MainActivity.sendAudioResultToFlutter("⏹ Recording stopped")
    }

    private fun createNewWavFile(): File {
        val stamp = SimpleDateFormat("yyyyMMdd_HHmmss_SSS", Locale.US).format(Date())
        val uuid = UUID.randomUUID().toString().substring(0, 8)
        val fileName = "chunk_${stamp}_$uuid.wav"
        val dir = File(filesDir, "chunks")
        if (!dir.exists()) dir.mkdirs()
        val f = File(dir, fileName)
        if (f.exists()) f.delete()
        return f
    }

    private fun ShortArrayToByteArray(data: ShortArray, count: Int): ByteArray {
        val out = ByteArray(count * 2)
        var j = 0
        for (i in 0 until count) {
            val v = data[i].toInt()
            out[j++] = (v and 0xFF).toByte()
            out[j++] = ((v shr 8) and 0xFF).toByte()
        }
        return out
    }

    // ------------------------------------------------------------------------------------
    // WAV header helpers
    // ------------------------------------------------------------------------------------
    private fun writeWavHeader(raf: RandomAccessFile, sampleRate: Int, channels: Int, bytesPerSample: Int) {
        raf.seek(0)
        val byteRate = sampleRate * channels * bytesPerSample
        val blockAlign = channels * bytesPerSample

        raf.writeBytes("RIFF")
        raf.writeIntLE(0)
        raf.writeBytes("WAVE")

        raf.writeBytes("fmt ")
        raf.writeIntLE(16)
        raf.writeShortLE(1)
        raf.writeShortLE(channels)
        raf.writeIntLE(sampleRate)
        raf.writeIntLE(byteRate)
        raf.writeShortLE(blockAlign)
        raf.writeShortLE(bytesPerSample * 8)

        raf.writeBytes("data")
        raf.writeIntLE(0)
    }

    private fun finalizeWavHeaderAndClose(raf: RandomAccessFile, file: File) {
        val totalLen = raf.length().toInt()
        val dataLen = totalLen - 44

        raf.seek(4)
        raf.writeIntLE(36 + dataLen)

        raf.seek(40)
        raf.writeIntLE(dataLen)

        raf.close()
        Log.i(TAG, "Finalized WAV: ${file.name} (${dataLen} bytes audio)")
    }

    private fun RandomAccessFile.writeIntLE(v: Int) {
        write(byteArrayOf(
            (v and 0xFF).toByte(),
            ((v shr 8) and 0xFF).toByte(),
            ((v shr 16) and 0xFF).toByte(),
            ((v shr 24) and 0xFF).toByte()
        ))
    }
    private fun RandomAccessFile.writeShortLE(v: Int) {
        write(byteArrayOf(
            (v and 0xFF).toByte(),
            ((v shr 8) and 0xFF).toByte()
        ))
    }

    // ------------------------------------------------------------------------------------
    // Uploads
    // ------------------------------------------------------------------------------------
    private fun safeUpload(file: File) {
        try {
            uploadMultipart(file, uploadUrl)
            Log.i(TAG, "Uploaded: ${file.name}")
            MainActivity.sendAudioResultToFlutter("✅ Upload success: ${file.name}")
        } catch (t: Throwable) {
            Log.e(TAG, "Upload failed for ${file.name}: ${t.message}")
            MainActivity.sendAudioResultToFlutter("❌ Upload failed: ${file.name}")
        }
    }

    private fun uploadMultipart(file: File, urlStr: String) {
        val boundary = "----EvenAI${UUID.randomUUID()}"
        val lineEnd = "\r\n"
        val twoHyphens = "--"

        val url = URL(urlStr)
        val conn = (url.openConnection() as HttpURLConnection).apply {
            doOutput = true
            doInput = true
            useCaches = false
            requestMethod = "POST"
            setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
            connectTimeout = 30_000
            readTimeout = 60_000
        }

        val out = DataOutputStream(conn.outputStream)

        out.writeBytes(twoHyphens + boundary + lineEnd)
        out.writeBytes("Content-Disposition: form-data; name=\"audio_file\"; filename=\"${file.name}\"$lineEnd")
        out.writeBytes("Content-Type: audio/wav$lineEnd$lineEnd")

        FileInputStream(file).use { fis ->
            val buf = ByteArray(64 * 1024)
            while (true) {
                val r = fis.read(buf)
                if (r <= 0) break
                out.write(buf, 0, r)
            }
        }
        out.writeBytes(lineEnd)

        val jobId = file.name.removeSuffix(".wav")
        out.writeBytes(twoHyphens + boundary + lineEnd)
        out.writeBytes("Content-Disposition: form-data; name=\"job_id\"$lineEnd$lineEnd")
        out.writeBytes(jobId + lineEnd)

        out.writeBytes(twoHyphens + boundary + twoHyphens + lineEnd)
        out.flush()

        val code = conn.responseCode
        if (code !in 200..299) {
            val err = conn.errorStream?.readBytes()?.toString(Charsets.UTF_8)
            throw RuntimeException("HTTP $code: $err")
        }
        conn.inputStream.close()
        out.close()
        conn.disconnect()
    }
}
