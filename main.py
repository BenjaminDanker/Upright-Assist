import time
import threading
import signal
import sys
import struct

from adafruit_motorkit import MotorKit
from gpiozero import Button

import pvporcupine
import pyaudio


SWITCH_GPIO_PIN = 17
RUN_SECONDS = 2.5
MOTOR_THROTTLE = 0.85
DIRECTION = 1
MOTOR_PORT = "motor1"
KEYWORD = "porcupine"
COOLDOWN_SECONDS = 1.0


kit = MotorKit()
stop_event = threading.Event()
motor_lock = threading.Lock()
last_activation_time = 0.0


def get_motor():
    motor = getattr(kit, MOTOR_PORT, None)
    if motor is None:
        raise RuntimeError("Invalid motor port")
    return motor


def motor_stop():
    with motor_lock:
        try:
            get_motor().throttle = 0
        except Exception:
            pass


def motor_run(seconds):
    global last_activation_time

    now = time.time()
    if now - last_activation_time < COOLDOWN_SECONDS:
        return
    last_activation_time = now

    with motor_lock:
        get_motor().throttle = MOTOR_THROTTLE * DIRECTION

    time.sleep(seconds)
    motor_stop()


def activate(source):
    if stop_event.is_set():
        return
    motor_run(RUN_SECONDS)


def setup_switch():
    button = Button(SWITCH_GPIO_PIN, pull_up=True, bounce_time=0.05)
    button.when_pressed = lambda: activate("switch")
    return button


def voice_listener():
    porcupine = pvporcupine.create(keywords=[KEYWORD])
    audio = pyaudio.PyAudio()

    stream = audio.open(
        rate=porcupine.sample_rate,
        channels=1,
        format=pyaudio.paInt16,
        input=True,
        frames_per_buffer=porcupine.frame_length
    )

    try:
        while not stop_event.is_set():
            pcm = stream.read(
                porcupine.frame_length,
                exception_on_overflow=False
            )
            pcm = struct.unpack_from(
                "h" * porcupine.frame_length,
                pcm
            )

            if porcupine.process(pcm) >= 0:
                activate("voice")

    finally:
        stream.stop_stream()
        stream.close()
        audio.terminate()
        porcupine.delete()


def shutdown_handler(signum, frame):
    stop_event.set()
    motor_stop()
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    motor_stop()
    setup_switch()

    listener_thread = threading.Thread(
        target=voice_listener,
        daemon=True
    )
    listener_thread.start()

    while not stop_event.is_set():
        time.sleep(0.2)


if __name__ == "__main__":
    main()
