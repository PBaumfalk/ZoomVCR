FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl ffmpeg xvfb x11vnc xdotool fluxbox xterm \
    pulseaudio pulseaudio-utils dbus-x11 python3 python3-venv \
    libglib2.0-0 libgl1 libpulse0 libxcb-shape0 libxcb-shm0 libxcb-xfixes0 \
    libxcb-randr0 libxcb-image0 libxcb-keysyms1 libxcb-xtest0 \
    libfontconfig1 libxi6 libsm6 libxrender1 libxcomposite1 libxslt1.1 \
    libsqlite3-0 ibus fonts-dejavu-core procps xclip \
    libegl1 libnss3 libnspr4 \
    tesseract-ocr tesseract-ocr-eng tesseract-ocr-deu && \
    curl -fsSL --retry 3 https://zoom.us/client/latest/zoom_amd64.deb -o /tmp/zoom.deb && \
    apt-get install -y --no-install-recommends /tmp/zoom.deb && \
    rm -f /tmp/zoom.deb && rm -rf /var/lib/apt/lists/*
# Firefox from Mozilla's official APT repository (Ubuntu's own package is a snap and does not run in Docker).
# Needed because the Zoom client signs in via the system browser and returns via a zoommtg:// link.
RUN apt-get update && apt-get install -y --no-install-recommends gnupg xdg-utils && \
    install -d -m 0755 /etc/apt/keyrings && \
    curl -fsSL --retry 3 https://packages.mozilla.org/apt/repo-signing-key.gpg -o /etc/apt/keyrings/packages.mozilla.org.asc && \
    echo "deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] https://packages.mozilla.org/apt mozilla main" > /etc/apt/sources.list.d/mozilla.list && \
    printf 'Package: *\nPin: origin packages.mozilla.org\nPin-Priority: 1000\n' > /etc/apt/preferences.d/mozilla && \
    apt-get update && apt-get install -y --no-install-recommends firefox && \
    rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/agent && /opt/agent/bin/pip install --no-cache-dir 'fastapi>=0.115,<1' 'uvicorn>=0.30,<1' 'pydantic>=2,<3' 'pillow>=11,<13' 'pytesseract>=0.3.13' && \
    useradd --create-home --uid 10001 --shell /bin/bash zoomvcr && \
    install -d -o zoomvcr -g zoomvcr /data/recordings /home/zoomvcr/.vnc
WORKDIR /app
COPY desktop/start.sh /app/start.sh
COPY backend/zoomvcr/desktop_agent.py /app/desktop_agent.py
COPY backend/zoomvcr/display_name.py /app/display_name.py
COPY backend/zoomvcr/zoom_name_gui.py /app/zoom_name_gui.py
RUN chmod 755 /app/start.sh
ENV DISPLAY=:99 HOME=/home/zoomvcr XDG_RUNTIME_DIR=/tmp/runtime-zoomvcr BROWSER=firefox
USER zoomvcr
EXPOSE 8765 5900
CMD ["/app/start.sh"]
