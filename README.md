---
title: "NightSky Whisperer: An Offline AI Stargazing Companion on Arduino UNO Q"
published: false
tags: devchallenge, hf26challenge, ai, opensource
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge — Week 1: Touch Grass](https://dev.to/challenges/hacktoberfest-week1-2026-10-05).*

# NightSky Whisperer 🌌
### Less screen time. More time under the stars.

<img width="500" alt="image" src="https://github.com/user-attachments/assets/a0adc919-792b-4cff-9af4-33a99ccb2788" />


What if exploring the night sky felt less like operating an app and more like having an astronomy companion beside you?

Imagine stepping outside, pointing your phone toward the sky, and asking:

**“Find Betelgeuse.”**

Instead of searching through menus and reading information on a screen, NightSky Whisperer is designed to respond through voice, calculate where the star should be, and guide your attention using a tiny LED matrix.

The idea behind this project is simple: **AI should help us experience the world, not give us another reason to stare at a screen.**

## What I Built

NightSky Whisperer is a local-first astronomy companion built around an **Arduino UNO Q with 4 GB RAM and an Android phone**.

The phone provides location, orientation sensors, and microphone input. The UNO Q runs the local AI and astronomy services, while its onboard LED matrix provides a physical interface for navigation and status feedback.

The project combines:

- **Offline speech recognition** using Whisper through `whisper.cpp`.
- **Local AI conversations** using a quantized Gemma 3 1B model served by `llama.cpp`.
- **Spoken responses** generated using Piper TTS and played through the phone.
- **Astronomical calculations** using Astropy to transform celestial coordinates into local altitude and azimuth.
- **Phone-based pointing** using live location and orientation telemetry.
- **Physical LED animations** for directional guidance, listening, thinking, speaking, target acquisition, and safety warnings.

Rather than building another astronomy chatbot that only returns text, I'm exploring how local AI can connect conversation to a real-world activity.

## Demo

**Source code:** [NightSky Whisperer on GitHub](https://github.com/pixelcrisscross/nightsky-whisperer.git)

The intended live demonstration starts with a spoken request to find a bright star. The system transcribes the request, produces a spoken response, calculates the target's position, and uses the LED matrix to communicate guidance or a safety warning.

A representative test also checks what happens when a star is below the horizon. Instead of issuing normal directional guidance, the astronomy service identifies that the target is geometrically below the horizon and marks navigation as non-actionable.

The project is running on real hardware, and I am continuing to validate the complete voice-to-navigation experience and physical direction mapping.

## How I Built It

### 1. Local speech and AI

The voice pipeline uses three components:

**Whisper through `whisper.cpp`** transcribes spoken questions locally.

**Gemma 3 1B through `llama.cpp`** generates conversational answers on the UNO Q, without requiring a hosted language-model API for each question.

**Piper TTS** converts the response into speech, which is streamed back to the Android phone for playback.

This gives me control over the models, prompts, runtime, and integration between the different components.

### 2. Real-time astronomy

A star's celestial coordinates alone aren't enough to tell someone where to point their phone. Its local position depends on the observer's location and the observation time.

I integrated Astropy to transform star coordinates into horizontal coordinates:

- **Altitude:** how far above or below the geometric horizon the target is.
- **Azimuth:** its compass direction, measured from north.
- **Angular separation:** how far the target is from the phone's current pointing direction.

The guidance engine compares the calculated target position with the phone's calibrated pointing direction and produces a coarse directional hint.

One important distinction: calculating that a star is above the horizon does not guarantee that it is visually observable. Daylight, clouds, buildings, glare, and light pollution can all interfere.

### 3. Connecting the phone and UNO Q

The Android phone streams location and orientation telemetry to a FastAPI server over WebSocket.

The server exposes endpoints for selecting stars, requesting guidance, controlling the matrix, and monitoring system state. The phone also supplies audio for the local speech pipeline.

The architecture is designed to keep core AI inference and astronomy calculations local. The phone and UNO Q still need a working local connection, and downloading updated data or software can require internet access.

### 4. The physical interface

The UNO Q's onboard LED matrix has only 8 rows and 13 columns. Designing useful animations at that resolution is an interesting constraint.

The firmware includes distinct states for directional arrows, listening, thinking, speaking, a target-acquired effect, a cosmic Easter egg, and a below-horizon warning.

A key design requirement is **priority**: active navigation and safety warnings should not be overwritten by decorative or conversational animations.

## Why Open Innovation Matters

For an application designed to encourage outdoor exploration, I don't want internet access to be a mandatory dependency for every conversation.

Building around open-source software and an open-weight language model provides several advantages.

**Privacy by design**

Speech recognition and language-model inference can happen locally. A spoken astronomy question does not inherently need to be sent to a cloud AI provider.

**Control over the technology**

I can inspect the code, change command routing, adjust prompts, replace models, and improve the behaviour of the assistant without depending on a proprietary API's capabilities or pricing.

**A path toward offline use**

With the required models, software, and astronomy data already installed, the core voice-and-guidance pipeline is designed to operate locally. The phone-to-device connection must still be available unless another local transport is used.

**AI that interacts with the physical world**

The open components are not merely generating text. They are part of a system that combines speech, astronomical computation, mobile sensors, and a physical display to support an activity outside the screen.

Open innovation gave me the flexibility to build and change the whole stack rather than treating the language model as a black box.

## Challenges and What I Learned

The hardest part has not been getting an AI model to explain a star. It has been making every component work together reliably.

For example, a voice assistant can correctly recognize “Find Betelgeuse” and generate an explanation without actually starting navigation. Recognizing a target, selecting it, activating the navigation session, checking sky conditions, and updating the matrix are separate operations that must be connected deliberately.

Astronomy introduces another challenge: correct coordinates do not automatically mean correct physical guidance. Sensor calibration, phone orientation, mount geometry, and matrix direction mapping all need validation on the assembled hardware.

I have also observed that local model latency can be significant on this device. Reducing the time between a spoken command and the physical response is an important next step.

These challenges have shaped the project into more than a chatbot. The goal is a complete system whose calculations, actions, and physical feedback can all be tested.

## What's Next?

I want NightSky Whisperer to grow into a more capable personal astronomy companion.

My next priorities are:

- Complete and validate voice commands that start and stop star navigation.
- Verify physical left, right, up, and down guidance against the mounted phone.
- Improve model latency and the time from voice input to response.
- Expand the catalogue and add richer constellation exploration.
- Improve recovery after power-on and loss of phone connectivity.
- Test the system outdoors under actual nighttime conditions.

The longer-term vision is an assistant that helps people explore stars, constellations, planets, and other celestial objects through conversation and physical guidance—with the screen playing as small a role as possible.

## Try It and Follow Along

**GitHub:** [https://github.com/pixelcrisscross/nightsky-whisperer.git](https://github.com/pixelcrisscross/nightsky-whisperer.git)

I'm building NightSky Whisperer as a hardware-and-AI experiment, and real-world testing is an essential part of making it useful. The next milestone is a complete outdoor demonstration: ask a question, select a target, and verify that the physical guidance helps you find it safely.

**What would you add to an offline AI astronomy companion?** Constellation identification, satellite passes, meteor-shower alerts, or a conversational guide to the night sky?

I'd love to hear your ideas.

#Hacktoberfest #OpenSourceAI #Arduino #Astronomy
