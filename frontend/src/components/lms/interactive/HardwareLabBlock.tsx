import { useState, useRef, useEffect } from "react";
import {
  CheckCircle2,
  Cpu,
  Cable,
  Network,
  Activity,
  Thermometer,
  Tv,
  Compass,
  HardDrive,
  Disc,
  Music,
  Lightbulb,
  Send,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { ContentLab } from "@/api/lms";
import { MarkdownContent } from "@/components/lms/MarkdownContent";

interface HardwareLabBlockProps {
  content: ContentLab;
  onComplete: () => void;
  isCompleted?: boolean;
}

export function HardwareLabBlock({ content, onComplete, isCompleted = false }: HardwareLabBlockProps) {
  const labType = (content.lab_type || "uart").toLowerCase();

  return (
    <Card className="p-4 sm:p-6 flex flex-col gap-6 bg-card border border-border rounded-2xl shadow-sm">
      <div className="flex items-center justify-between border-b border-border pb-4">
        <div className="flex items-center gap-2">
          {labType === "uart" && <Cable className="size-5 text-teal-400" />}
          {labType === "i2c" && <Cpu className="size-5 text-purple-400" />}
          {labType === "can" && <Network className="size-5 text-rose-400" />}
          {labType === "spi" && <Activity className="size-5 text-amber-400" />}
          <h3 className="font-semibold text-lg text-foreground">
            {content.title || `${labType.toUpperCase()} Interactive Lab`}
          </h3>
        </div>
      </div>

      {(content.markdown || content.instructions) && (
        <div className="p-4 sm:p-5 bg-muted/30 rounded-xl border border-border/60 overflow-hidden">
          <MarkdownContent content={content.markdown || content.instructions || ""} />
        </div>
      )}

      {labType === "uart" && <UartLabSimulator onPass={onComplete} isCompleted={isCompleted} />}
      {labType === "i2c" && <I2cLabSimulator onPass={onComplete} isCompleted={isCompleted} />}
      {labType === "can" && <CanLabSimulator onPass={onComplete} isCompleted={isCompleted} />}
      {labType === "spi" && <SpiLabSimulator onPass={onComplete} isCompleted={isCompleted} />}
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. UART LAB SIMULATOR (Cross-Over Wiring with SVG Lines)
// ─────────────────────────────────────────────────────────────────────────────
interface UartConnection {
  from: string; // e.g. "mcu-tx"
  to: string;   // e.g. "mod-rx"
}

function UartLabSimulator({ onPass, isCompleted }: { onPass: () => void; isCompleted: boolean }) {
  const [selectedPin, setSelectedPin] = useState<string | null>(null);
  const [connections, setConnections] = useState<UartConnection[]>(
    isCompleted
      ? [
          { from: "mcu-tx", to: "mod-rx" },
          { from: "mcu-rx", to: "mod-tx" },
          { from: "mcu-gnd", to: "mod-gnd" },
        ]
      : []
  );
  const [tempMousePos, setTempMousePos] = useState<{ x: number; y: number } | null>(null);
  const [feedback, setFeedback] = useState<{ msg: string; color: string }>(
    isCompleted
      ? { msg: "✅ Communication link verified! Transmit and receive lines cross-connected.", color: "text-green-400 font-bold" }
      : { msg: "Tap a pin on left, then tap destination pin on right.", color: "text-gray-400 italic" }
  );
  const [verified, setVerified] = useState<boolean>(isCompleted);
  const [, setTick] = useState(0);

  const containerRef = useRef<HTMLDivElement>(null);
  const pinRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const registerPinRef = (id: string, el: HTMLDivElement | null) => {
    pinRefs.current[id] = el;
  };

  const getPinCenter = (pinId: string) => {
    const el = pinRefs.current[pinId];
    const container = containerRef.current;
    if (!el || !container) return { x: 0, y: 0 };
    const elRect = el.getBoundingClientRect();
    const contRect = container.getBoundingClientRect();
    return {
      x: elRect.left + elRect.width / 2 - contRect.left,
      y: elRect.top + elRect.height / 2 - contRect.top,
    };
  };

  // Re-measure pin coordinates on container resize, window resize, or orientation change
  useEffect(() => {
    const timer = setTimeout(() => {
      setTick((t) => t + 1);
    }, 40);

    const container = containerRef.current;
    if (!container) return () => clearTimeout(timer);

    const ro = new ResizeObserver(() => {
      setTick((t) => t + 1);
    });
    ro.observe(container);

    const onResize = () => setTick((t) => t + 1);
    window.addEventListener("resize", onResize);
    window.addEventListener("orientationchange", onResize);

    return () => {
      clearTimeout(timer);
      ro.disconnect();
      window.removeEventListener("resize", onResize);
      window.removeEventListener("orientationchange", onResize);
    };
  }, []);

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!selectedPin || !containerRef.current) return;
    const contRect = containerRef.current.getBoundingClientRect();
    setTempMousePos({
      x: e.clientX - contRect.left,
      y: e.clientY - contRect.top,
    });
  };

  const handlePinClick = (pinId: string) => {
    if (verified) return;

    // Check if pin is already connected
    const alreadyConnected = connections.some((c) => c.from === pinId || c.to === pinId);
    if (alreadyConnected) {
      setFeedback({ msg: "❌ Pin already connected! Click Reset to try again.", color: "text-red-400 font-semibold" });
      return;
    }

    if (!selectedPin) {
      // First click
      setSelectedPin(pinId);
      setFeedback({ msg: "Now tap destination pin on the other device...", color: "text-blue-300 animate-pulse font-semibold" });
    } else {
      // Second click
      const from = selectedPin;
      const to = pinId;

      if (from === to) {
        setSelectedPin(null);
        setTempMousePos(null);
        return;
      }

      const fromSide = from.startsWith("mcu") ? "mcu" : "mod";
      const toSide = to.startsWith("mcu") ? "mcu" : "mod";

      if (fromSide === toSide) {
        setFeedback({ msg: "❌ Connect to the OTHER device!", color: "text-red-400 font-semibold" });
        setSelectedPin(null);
        setTempMousePos(null);
        return;
      }

      // Order always MCU -> MOD for consistent checking
      const newConn: UartConnection = fromSide === "mcu" ? { from, to } : { from: to, to: from };
      setConnections((prev) => [...prev, newConn]);
      setSelectedPin(null);
      setTempMousePos(null);
      setFeedback({ msg: "Wire connected.", color: "text-gray-300" });
      setTick((t) => t + 1);
    }
  };

  const handleReset = () => {
    setConnections([]);
    setSelectedPin(null);
    setTempMousePos(null);
    setVerified(false);
    setFeedback({ msg: "Connect TX, RX, and GND correctly.", color: "text-gray-400 italic" });
    setTick((t) => t + 1);
  };

  const handleVerify = () => {
    let tx_rx = false;
    let rx_tx = false;
    let gnd_gnd = false;
    let errors = false;

    connections.forEach((c) => {
      const p1Type = c.from.split("-")[1]; // e.g. "tx"
      const p2Type = c.to.split("-")[1];   // e.g. "rx"

      if (p1Type === "gnd" && p2Type === "gnd") {
        gnd_gnd = true;
      } else if (p1Type === "tx" && p2Type === "rx") {
        tx_rx = true;
      } else if (p1Type === "rx" && p2Type === "tx") {
        rx_tx = true;
      } else {
        errors = true;
      }
    });

    if (errors) {
      setFeedback({ msg: "❌ Check wires! TX goes to RX, GND goes to GND.", color: "text-red-400 font-bold" });
    } else if (tx_rx && rx_tx && gnd_gnd) {
      setVerified(true);
      setFeedback({ msg: "✅ Excellent! Communication link established.", color: "text-green-400 font-bold" });
    } else if (!gnd_gnd) {
      setFeedback({ msg: "⚠️ Don't forget Ground (GND)!", color: "text-yellow-400 font-semibold" });
    } else {
      setFeedback({ msg: "⚠️ Incomplete. Connect both TX->RX and RX->TX.", color: "text-yellow-400 font-semibold" });
    }
  };

  const pinDotStyle = "w-4 h-4 rounded-full border-2 border-white shadow-[0_0_10px_white] transition-transform";

  return (
    <div className="bg-black/40 border border-purple-500/30 rounded-xl p-4 sm:p-5 select-none flex flex-col gap-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h4 className="font-bold text-purple-300 flex items-center gap-2 text-sm sm:text-base">
          <Cable className="w-5 h-5 text-purple-400" />
          UART Lab: Connect the Dots
        </h4>
        <div className="text-xs text-gray-400">
          Tap a pin on left, then tap a pin on right.
        </div>
      </div>

      {/* Visual Canvas Area */}
      <div
        ref={containerRef}
        onMouseMove={handleMouseMove}
        className="relative h-64 sm:h-80 bg-[#1a0526] border border-gray-800 rounded-lg overflow-hidden flex items-center justify-between px-3 sm:px-12 select-none"
      >
        {/* SVG Wire Layer */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none z-10">
          {connections.map((c, i) => {
            const start = getPinCenter(c.from);
            const end = getPinCenter(c.to);
            return (
              <line
                key={i}
                x1={start.x}
                y1={start.y}
                x2={end.x}
                y2={end.y}
                stroke="#22d3ee"
                strokeWidth="3.5"
                className="drop-shadow-[0_0_8px_rgba(34,211,238,0.85)]"
              />
            );
          })}

          {selectedPin && tempMousePos && (
            <line
              x1={getPinCenter(selectedPin).x}
              y1={getPinCenter(selectedPin).y}
              x2={tempMousePos.x}
              y2={tempMousePos.y}
              stroke="rgba(255,255,255,0.85)"
              strokeWidth="3"
              strokeDasharray="5,5"
            />
          )}
        </svg>

        {/* Microcontroller (Left) */}
        <div className="w-28 sm:w-36 bg-purple-900/40 border border-purple-500 rounded-lg p-2.5 sm:p-4 z-20 shadow-lg shadow-purple-950/50 shrink-0">
          <div className="text-center text-xs font-bold text-purple-300 mb-3 tracking-wide">
            Microcontroller
          </div>
          <div className="flex flex-col gap-3.5 sm:gap-4 items-end pr-1 sm:pr-2">
            <button
              type="button"
              onClick={() => handlePinClick("mcu-tx")}
              className="flex items-center gap-1.5 p-1 -m-1 rounded-md touch-manipulation focus:outline-none group/pin cursor-pointer"
            >
              <span className="text-[10px] sm:text-[11px] font-mono text-gray-400 group-hover/pin:text-white">TX</span>
              <div
                ref={(el) => registerPinRef("mcu-tx", el)}
                className={`${pinDotStyle} ${
                  connections.some((c) => c.from === "mcu-tx" || c.to === "mcu-tx")
                    ? "bg-green-500 ring-2 ring-green-300"
                    : selectedPin === "mcu-tx"
                    ? "bg-yellow-400 ring-4 ring-yellow-200 animate-pulse scale-125"
                    : "bg-green-500"
                }`}
              />
            </button>
            <button
              type="button"
              onClick={() => handlePinClick("mcu-rx")}
              className="flex items-center gap-1.5 p-1 -m-1 rounded-md touch-manipulation focus:outline-none group/pin cursor-pointer"
            >
              <span className="text-[10px] sm:text-[11px] font-mono text-gray-400 group-hover/pin:text-white">RX</span>
              <div
                ref={(el) => registerPinRef("mcu-rx", el)}
                className={`${pinDotStyle} ${
                  connections.some((c) => c.from === "mcu-rx" || c.to === "mcu-rx")
                    ? "bg-blue-500 ring-2 ring-blue-300"
                    : selectedPin === "mcu-rx"
                    ? "bg-yellow-400 ring-4 ring-yellow-200 animate-pulse scale-125"
                    : "bg-blue-500"
                }`}
              />
            </button>
            <button
              type="button"
              onClick={() => handlePinClick("mcu-gnd")}
              className="flex items-center gap-1.5 p-1 -m-1 rounded-md touch-manipulation focus:outline-none group/pin cursor-pointer"
            >
              <span className="text-[10px] sm:text-[11px] font-mono text-gray-400 group-hover/pin:text-white">GND</span>
              <div
                ref={(el) => registerPinRef("mcu-gnd", el)}
                className={`${pinDotStyle} ${
                  connections.some((c) => c.from === "mcu-gnd" || c.to === "mcu-gnd")
                    ? "bg-gray-500 ring-2 ring-gray-300"
                    : selectedPin === "mcu-gnd"
                    ? "bg-yellow-400 ring-4 ring-yellow-200 animate-pulse scale-125"
                    : "bg-gray-500"
                }`}
              />
            </button>
          </div>
        </div>

        {/* Module (Right) */}
        <div className="w-28 sm:w-36 bg-teal-900/40 border border-teal-500 rounded-lg p-2.5 sm:p-4 z-20 shadow-lg shadow-teal-950/50 shrink-0">
          <div className="text-center text-xs font-bold text-teal-300 mb-3 tracking-wide">
            GPS Module
          </div>
          <div className="flex flex-col gap-3.5 sm:gap-4 items-start pl-1 sm:pl-2">
            <button
              type="button"
              onClick={() => handlePinClick("mod-tx")}
              className="flex items-center gap-1.5 p-1 -m-1 rounded-md touch-manipulation focus:outline-none group/pin cursor-pointer"
            >
              <div
                ref={(el) => registerPinRef("mod-tx", el)}
                className={`${pinDotStyle} ${
                  connections.some((c) => c.from === "mod-tx" || c.to === "mod-tx")
                    ? "bg-green-500 ring-2 ring-green-300"
                    : selectedPin === "mod-tx"
                    ? "bg-yellow-400 ring-4 ring-yellow-200 animate-pulse scale-125"
                    : "bg-green-500"
                }`}
              />
              <span className="text-[10px] sm:text-[11px] font-mono text-gray-400 group-hover/pin:text-white">TX</span>
            </button>
            <button
              type="button"
              onClick={() => handlePinClick("mod-rx")}
              className="flex items-center gap-1.5 p-1 -m-1 rounded-md touch-manipulation focus:outline-none group/pin cursor-pointer"
            >
              <div
                ref={(el) => registerPinRef("mod-rx", el)}
                className={`${pinDotStyle} ${
                  connections.some((c) => c.from === "mod-rx" || c.to === "mod-rx")
                    ? "bg-blue-500 ring-2 ring-blue-300"
                    : selectedPin === "mod-rx"
                    ? "bg-yellow-400 ring-4 ring-yellow-200 animate-pulse scale-125"
                    : "bg-blue-500"
                }`}
              />
              <span className="text-[10px] sm:text-[11px] font-mono text-gray-400 group-hover/pin:text-white">RX</span>
            </button>
            <button
              type="button"
              onClick={() => handlePinClick("mod-gnd")}
              className="flex items-center gap-1.5 p-1 -m-1 rounded-md touch-manipulation focus:outline-none group/pin cursor-pointer"
            >
              <div
                ref={(el) => registerPinRef("mod-gnd", el)}
                className={`${pinDotStyle} ${
                  connections.some((c) => c.from === "mod-gnd" || c.to === "mod-gnd")
                    ? "bg-gray-500 ring-2 ring-gray-300"
                    : selectedPin === "mod-gnd"
                    ? "bg-yellow-400 ring-4 ring-yellow-200 animate-pulse scale-125"
                    : "bg-gray-500"
                }`}
              />
              <span className="text-[10px] sm:text-[11px] font-mono text-gray-400 group-hover/pin:text-white">GND</span>
            </button>
          </div>
        </div>
      </div>

      {/* Feedback & Actions */}
      <div className="flex flex-col sm:flex-row justify-between items-center gap-3 pt-1">
        <div className={`text-sm ${feedback.color}`}>
          {feedback.msg}
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleReset}
            className="text-red-400 text-xs hover:text-red-300 underline font-medium"
          >
            Reset
          </button>
          {!verified ? (
            <button
              onClick={handleVerify}
              disabled={connections.length < 3}
              className="bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white px-4 py-1.5 rounded text-sm font-bold transition-colors shadow-lg shadow-green-900/20"
            >
              Verify Connection
            </button>
          ) : (
            <Button onClick={onPass} className="bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs h-8">
              <CheckCircle2 className="size-4 mr-1.5" /> Complete Lab
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. I2C LAB SIMULATOR (Architecture Multi-Drop Bus Builder)
// ─────────────────────────────────────────────────────────────────────────────
interface I2cDevice {
  role: "master" | "slave";
  name: string;
  icon: string;
  color: string;
}

function I2cLabSimulator({ onPass, isCompleted }: { onPass: () => void; isCompleted: boolean }) {
  const [devices, setDevices] = useState<I2cDevice[]>(
    isCompleted
      ? [
          { role: "master", name: "MCU (Master)", icon: "cpu", color: "text-purple-400" },
          { role: "slave", name: "TMP102", icon: "thermometer", color: "text-teal-400" },
          { role: "slave", name: "OLED", icon: "monitor", color: "text-teal-400" },
        ]
      : []
  );
  const [selectedType, setSelectedType] = useState<string>("master");
  const [feedback, setFeedback] = useState<{ msg: string; color: string }>(
    isCompleted
      ? { msg: "✅ SUCCESS! Master connected to 2 device(s).", color: "text-green-400 font-bold" }
      : { msg: "Add a Master Controller to start.", color: "text-gray-400 italic" }
  );
  const [verified, setVerified] = useState<boolean>(isCompleted);

  const handleAddDevice = () => {
    if (verified) return;
    const hasMaster = devices.some((d) => d.role === "master");

    if (selectedType === "master") {
      if (hasMaster) {
        setFeedback({ msg: "⚠️ Only one Master device is allowed!", color: "text-yellow-400 font-semibold" });
        return;
      }
      setDevices((prev) => [
        ...prev,
        { role: "master", name: "MCU (Master)", icon: "cpu", color: "text-purple-400" },
      ]);
    } else {
      if (devices.length >= 5) {
        setFeedback({ msg: "⚠️ Bus is full! Max 5 devices.", color: "text-yellow-400 font-semibold" });
        return;
      }
      let name = "Sensor";
      let icon = "activity";
      if (selectedType === "temp") { name = "TMP102"; icon = "thermometer"; }
      if (selectedType === "display") { name = "OLED"; icon = "monitor"; }
      if (selectedType === "gyro") { name = "IMU"; icon = "compass"; }

      setDevices((prev) => [
        ...prev,
        { role: "slave", name, icon, color: "text-teal-400" },
      ]);
    }
    setFeedback({ msg: "Device added to bus.", color: "text-gray-300" });
  };

  const handleReset = () => {
    setDevices([]);
    setVerified(false);
    setFeedback({ msg: "Lab reset. Add a Master Controller to start.", color: "text-gray-400 italic" });
  };

  const handleVerify = () => {
    const hasMaster = devices.some((d) => d.role === "master");
    const slaveCount = devices.filter((d) => d.role === "slave").length;

    if (!hasMaster) {
      setFeedback({ msg: "❌ Missing a Master Controller!", color: "text-red-400 font-bold" });
    } else if (slaveCount === 0) {
      setFeedback({ msg: "❌ The Master is lonely. Add some sensors!", color: "text-red-400 font-bold" });
    } else {
      setVerified(true);
      setFeedback({ msg: `✅ SUCCESS! Master connected to ${slaveCount} device(s).`, color: "text-green-400 font-bold" });
    }
  };

  const renderIcon = (iconName: string) => {
    switch (iconName) {
      case "cpu": return <Cpu className="w-8 h-8 text-purple-400" />;
      case "thermometer": return <Thermometer className="w-8 h-8 text-teal-400" />;
      case "monitor": return <Tv className="w-8 h-8 text-teal-400" />;
      case "compass": return <Compass className="w-8 h-8 text-teal-400" />;
      default: return <Activity className="w-8 h-8 text-teal-400" />;
    }
  };

  return (
    <div className="bg-black/40 border border-purple-500/30 rounded-xl p-4 sm:p-5 select-none flex flex-col gap-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h4 className="font-bold text-purple-300 flex items-center gap-2 text-sm sm:text-base">
          <Cpu className="w-5 h-5 text-purple-400" />
          I2C Lab: Build the Network
        </h4>
        <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap w-full sm:w-auto">
          <select
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value)}
            disabled={verified}
            className="flex-1 sm:flex-initial bg-purple-900/50 border border-purple-500/30 rounded px-2.5 py-1 text-xs sm:text-sm text-white focus:outline-none"
          >
            <option value="master">Microcontroller (Master)</option>
            <option value="temp">Temp Sensor (Slave)</option>
            <option value="display">OLED Screen (Slave)</option>
            <option value="gyro">Gyroscope (Slave)</option>
          </select>
          <button
            onClick={handleAddDevice}
            disabled={verified}
            className="bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white px-3 py-1 rounded text-xs sm:text-sm font-bold transition-colors shrink-0"
          >
            + Add Device
          </button>
        </div>
      </div>

      {/* Visualization Area */}
      <div className="relative h-60 sm:h-72 bg-[#1a0526] border border-gray-800 rounded-lg overflow-x-auto overflow-y-hidden flex items-center">
        {/* Bus Lines */}
        <div className="absolute top-1/2 left-0 w-full min-w-[340px] h-8 -mt-4 flex flex-col justify-center space-y-2 pointer-events-none">
          <div className="w-full h-1 bg-yellow-400 shadow-[0_0_10px_rgba(250,204,21,0.5)] relative">
            <span className="absolute right-3 -top-4 text-[9px] sm:text-[10px] text-yellow-400 opacity-60 font-mono">
              SDA (Data)
            </span>
          </div>
          <div className="w-full h-1 bg-blue-400 shadow-[0_0_10px_rgba(96,165,250,0.5)] relative">
            <span className="absolute right-3 top-2 text-[9px] sm:text-[10px] text-blue-400 opacity-60 font-mono">
              SCL (Clock)
            </span>
          </div>
        </div>

        {/* Devices Container */}
        <div className="w-full min-w-[340px] flex items-center justify-around px-2 sm:px-8 py-4">
          {devices.length === 0 ? (
            <div className="text-gray-500 text-xs sm:text-sm italic">Add devices to start building...</div>
          ) : (
            devices.map((device, idx) => (
              <div
                key={idx}
                className={`relative group p-1.5 sm:p-2 rounded-lg bg-black/80 border ${
                  device.role === "master"
                    ? "border-purple-500 shadow-purple-500/20"
                    : "border-teal-500 shadow-teal-500/20"
                } border shadow-lg flex flex-col items-center gap-1.5 sm:gap-2 w-16 sm:w-24 transition-all shrink-0`}
              >
                {/* Drop Line to Bus */}
                <div className="absolute -top-7 sm:-top-8 w-0.5 h-7 sm:h-8 bg-gray-500 group-hover:bg-white transition-colors" />

                <div className="scale-75 sm:scale-100 origin-center">
                  {renderIcon(device.icon)}
                </div>
                <span className="text-[9px] sm:text-[10px] font-bold text-gray-300 text-center leading-tight">
                  {device.name}
                </span>
                <span
                  className={`text-[7px] sm:text-[8px] uppercase tracking-wider ${
                    device.role === "master"
                      ? "bg-purple-900 text-purple-200"
                      : "bg-teal-900 text-teal-200"
                  } px-1 sm:px-1.5 py-0.5 rounded font-mono font-bold`}
                >
                  {device.role}
                </span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Feedback & Actions */}
      <div className="flex flex-col sm:flex-row justify-between items-center gap-3 pt-1">
        <div className={`text-sm ${feedback.color}`}>
          {feedback.msg}
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleReset}
            className="text-red-400 text-xs hover:text-red-300 underline font-medium"
          >
            Reset
          </button>
          {!verified ? (
            <button
              onClick={handleVerify}
              className="bg-green-600 hover:bg-green-500 text-white px-4 py-1.5 rounded text-sm font-bold transition-colors shadow-lg shadow-green-900/20"
            >
              Check Connections
            </button>
          ) : (
            <Button onClick={onPass} className="bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs h-8">
              <CheckCircle2 className="size-4 mr-1.5" /> Complete Lab
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 3. CAN BUS LAB SIMULATOR (Group Chat with Broadcast Signal)
// ─────────────────────────────────────────────────────────────────────────────
interface CanNode {
  type: string;
  name: string;
  icon: string;
}

function CanLabSimulator({ onPass, isCompleted }: { onPass: () => void; isCompleted: boolean }) {
  const [nodes, setNodes] = useState<CanNode[]>(
    isCompleted
      ? [
          { type: "engine", name: "Engine Control Unit", icon: "cpu" },
          { type: "brakes", name: "ABS / Brakes", icon: "disc" },
          { type: "radio", name: "Radio / Infotainment", icon: "music" },
        ]
      : []
  );
  const [selectedType, setSelectedType] = useState<string>("engine");
  const [isBroadcasting, setIsBroadcasting] = useState<boolean>(false);
  const [feedback, setFeedback] = useState<{ msg: string; color: string }>(
    isCompleted
      ? { msg: "✅ Message received by ALL nodes! All nodes hear every message.", color: "text-green-400 font-bold" }
      : { msg: "All nodes hear every message!", color: "text-gray-400 italic" }
  );
  const [verified, setVerified] = useState<boolean>(isCompleted);

  const nodeOptions: Record<string, { name: string; icon: string }> = {
    engine: { name: "Engine Control Unit", icon: "cpu" },
    brakes: { name: "ABS / Brakes", icon: "disc" },
    radio: { name: "Radio / Infotainment", icon: "music" },
    lights: { name: "Headlights Controller", icon: "lightbulb" },
  };

  const handleAddNode = () => {
    if (verified) return;
    if (nodes.length >= 4) {
      setFeedback({ msg: "⚠️ Bus is crowded! Max 4 nodes.", color: "text-yellow-400 font-semibold" });
      return;
    }
    const info = nodeOptions[selectedType] || { name: "Node", icon: "box" };
    setNodes((prev) => [...prev, { type: selectedType, name: info.name, icon: info.icon }]);
    setFeedback({ msg: "Node added. Connects to BOTH lines.", color: "text-gray-300" });
  };

  const handleReset = () => {
    setNodes([]);
    setIsBroadcasting(false);
    setVerified(false);
    setFeedback({ msg: "All nodes hear every message!", color: "text-gray-400 italic" });
  };

  const handleBroadcast = () => {
    if (nodes.length < 2) {
      setFeedback({ msg: "⚠️ Need at least 2 nodes to talk!", color: "text-yellow-400 font-semibold" });
      return;
    }

    setFeedback({ msg: "Broadcasting data packet...", color: "text-blue-400 animate-pulse font-semibold" });
    setIsBroadcasting(true);

    setTimeout(() => {
      setIsBroadcasting(false);
      setVerified(true);
      setFeedback({ msg: "✅ Message received by ALL nodes!", color: "text-green-400 font-bold" });
    }, 1500);
  };

  const renderNodeIcon = (iconName: string) => {
    switch (iconName) {
      case "cpu": return <Cpu className="w-6 h-6 text-gray-300 mb-1" />;
      case "disc": return <Disc className="w-6 h-6 text-gray-300 mb-1" />;
      case "music": return <Music className="w-6 h-6 text-gray-300 mb-1" />;
      case "lightbulb": return <Lightbulb className="w-6 h-6 text-gray-300 mb-1" />;
      default: return <Cpu className="w-6 h-6 text-gray-300 mb-1" />;
    }
  };

  return (
    <div className="bg-black/40 border border-purple-500/30 rounded-xl p-4 sm:p-5 select-none flex flex-col gap-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h4 className="font-bold text-purple-300 flex items-center gap-2 text-sm sm:text-base">
          <Network className="w-5 h-5 text-purple-400" />
          CAN Bus: The Group Chat
        </h4>
        <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap w-full sm:w-auto">
          <select
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value)}
            disabled={verified}
            className="flex-1 sm:flex-initial bg-purple-900/50 border border-purple-500/30 rounded px-2.5 py-1 text-xs sm:text-sm text-white focus:outline-none"
          >
            <option value="engine">Engine Control Unit</option>
            <option value="brakes">ABS / Brakes</option>
            <option value="radio">Radio / Infotainment</option>
            <option value="lights">Headlights Controller</option>
          </select>
          <button
            onClick={handleAddNode}
            disabled={verified}
            className="bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white px-3 py-1 rounded text-xs sm:text-sm font-bold transition-colors shrink-0"
          >
            + Add Node
          </button>
        </div>
      </div>

      {/* Bus Visualization */}
      <div className="relative h-56 sm:h-64 bg-[#1a0526] border border-gray-800 rounded-lg overflow-x-auto overflow-y-hidden flex items-center justify-center">
        {/* The Bus Backbone */}
        <div className="absolute w-[92%] min-w-[300px] h-8 flex flex-col justify-center space-y-2 z-0">
          {/* CAN H */}
          <div className="w-full h-1 bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.5)] relative">
            <div className="absolute -left-2 -top-1 w-2 h-3 bg-gray-500 rounded-l" title="Terminator 120Ω" />
            <div className="absolute -right-2 -top-1 w-2 h-3 bg-gray-500 rounded-r" title="Terminator 120Ω" />
            <span className="absolute left-1/2 -top-4 text-[9px] sm:text-[10px] text-red-500 -translate-x-1/2 font-mono whitespace-nowrap">
              CAN High
            </span>
          </div>
          {/* CAN L */}
          <div className="w-full h-1 bg-green-500 shadow-[0_0_10px_rgba(34,197,94,0.5)] relative">
            <div className="absolute -left-2 -top-1 w-2 h-3 bg-gray-500 rounded-l" />
            <div className="absolute -right-2 -top-1 w-2 h-3 bg-gray-500 rounded-r" />
            <span className="absolute left-1/2 top-2 text-[9px] sm:text-[10px] text-green-500 -translate-x-1/2 font-mono whitespace-nowrap">
              CAN Low
            </span>
          </div>
        </div>

        {/* Signal Animation Layer */}
        {isBroadcasting && (
          <div className="absolute w-[92%] min-w-[300px] h-8 z-10 pointer-events-none">
            <div className="w-full h-full bg-yellow-400/30 animate-pulse rounded shadow-[0_0_15px_rgba(250,204,21,0.8)]" />
          </div>
        )}

        {/* Nodes Container */}
        <div className="absolute inset-0 min-w-[300px] flex items-end justify-center gap-2 sm:gap-6 pb-3 z-20 pointer-events-none">
          {nodes.length === 0 ? (
            <div className="text-gray-500 text-xs sm:text-sm mb-8">Add nodes to the bus...</div>
          ) : (
            nodes.map((node, idx) => (
              <div key={idx} className="flex flex-col items-center group relative transition-transform">
                {/* Drop Line to Bus */}
                <div className="h-7 sm:h-8 w-0.5 bg-gray-500 mb-0 relative">
                  <div className="absolute -top-1 -left-1 w-2 h-2 bg-white rounded-full" />
                </div>

                <div
                  className={`border p-1.5 sm:p-2 rounded flex flex-col items-center w-16 sm:w-20 shadow-lg transition-all ${
                    isBroadcasting
                      ? "border-yellow-400 bg-yellow-900/60 shadow-[0_0_12px_rgba(250,204,21,0.4)]"
                      : "bg-gray-800 border-gray-600"
                  }`}
                >
                  <div className="scale-75 sm:scale-100 origin-center">
                    {renderNodeIcon(node.icon)}
                  </div>
                  <span className="text-[8px] sm:text-[9px] text-gray-300 text-center leading-tight">
                    {node.name}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Controls & Feedback */}
      <div className="flex flex-col sm:flex-row justify-between items-center gap-3 pt-1">
        <div className={`text-sm ${feedback.color}`}>
          {feedback.msg}
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleReset}
            className="text-red-400 text-xs hover:text-red-300 underline font-medium"
          >
            Reset
          </button>
          {!verified ? (
            <button
              onClick={handleBroadcast}
              disabled={isBroadcasting}
              className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-1.5 rounded text-sm font-bold transition-colors shadow-lg shadow-blue-900/20 flex items-center gap-1.5"
            >
              <Send className="w-3.5 h-3.5" /> Broadcast Message
            </button>
          ) : (
            <Button onClick={onPass} className="bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs h-8">
              <CheckCircle2 className="size-4 mr-1.5" /> Complete Lab
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 4. SPI LAB SIMULATOR (High-Speed Express with Full Duplex Flight Animation)
// ─────────────────────────────────────────────────────────────────────────────
function SpiLabSimulator({ onPass, isCompleted }: { onPass: () => void; isCompleted: boolean }) {
  const [selectedSlave, setSelectedSlave] = useState<number | null>(isCompleted ? 0 : null);
  const [isTransferring, setIsTransferring] = useState<boolean>(false);
  const [packetProgress, setPacketProgress] = useState<number>(0);
  const [feedback, setFeedback] = useState<{ msg: string; color: string }>(
    isCompleted
      ? { msg: "✅ Data exchange complete! (Full Duplex)", color: "text-green-400 font-bold" }
      : { msg: "Turn ON a Chip Select (CS) switch to talk to that device.", color: "text-gray-400 italic" }
  );
  const [verified, setVerified] = useState<boolean>(isCompleted);

  const slaves = [
    { name: "SD Card", icon: "hard-drive" },
    { name: "Display", icon: "monitor" },
    { name: "Sensor", icon: "thermometer" },
  ];

  const handleToggleCS = (index: number) => {
    if (verified) return;
    if (selectedSlave === index) {
      setSelectedSlave(null);
      setFeedback({ msg: "Device deselected.", color: "text-gray-400" });
    } else {
      setSelectedSlave(index);
      setFeedback({ msg: `Selected Slave ${index + 1}. High speed link ready.`, color: "text-green-400 font-semibold" });
    }
  };

  const handleReset = () => {
    setSelectedSlave(null);
    setIsTransferring(false);
    setPacketProgress(0);
    setVerified(false);
    setFeedback({ msg: "Turn ON a Chip Select (CS) switch to talk to that device.", color: "text-gray-400 italic" });
  };

  const handleTransfer = () => {
    if (selectedSlave === null) {
      setFeedback({ msg: "⚠️ Select a device (CS switch) first!", color: "text-yellow-400 font-semibold" });
      return;
    }

    setFeedback({ msg: "Transmitting Data chunks...", color: "text-blue-300 animate-pulse font-semibold" });
    setIsTransferring(true);
    setPacketProgress(0);

    const startTime = performance.now();
    const duration = 1000;

    const animate = (time: number) => {
      const elapsed = time - startTime;
      const progress = Math.min(1, elapsed / duration);
      setPacketProgress(progress);

      if (progress < 1) {
        requestAnimationFrame(animate);
      } else {
        setIsTransferring(false);
        setVerified(true);
        setFeedback({ msg: "✅ Data exchange complete! (Full Duplex)", color: "text-green-400 font-bold" });
      }
    };

    requestAnimationFrame(animate);
  };

  const renderSlaveIcon = (iconName: string, active: boolean) => {
    const color = active ? "text-green-300" : "text-gray-500";
    switch (iconName) {
      case "hard-drive": return <HardDrive className={`w-6 h-6 ${color} transition-colors`} />;
      case "monitor": return <Tv className={`w-6 h-6 ${color} transition-colors`} />;
      case "thermometer": return <Thermometer className={`w-6 h-6 ${color} transition-colors`} />;
      default: return <Activity className={`w-6 h-6 ${color} transition-colors`} />;
    }
  };

  return (
    <div className="bg-black/40 border border-purple-500/30 rounded-xl p-4 sm:p-5 select-none flex flex-col gap-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h4 className="font-bold text-purple-300 flex items-center gap-2 text-sm sm:text-base">
          <Activity className="w-5 h-5 text-purple-400" />
          SPI: The High-Speed Express
        </h4>
        <div className="text-xs text-gray-400">
          Turn ON a Chip Select (CS) switch to talk to that device.
        </div>
      </div>

      {/* Lab Viz */}
      <div className="relative h-64 sm:h-72 bg-[#1a0526] border border-gray-800 rounded-lg overflow-x-auto overflow-y-hidden flex items-center justify-between p-3 sm:p-4 px-3 sm:px-10">
        {/* Shared Bus Lines (Horizontal) */}
        <div className="absolute top-[40%] left-[26%] sm:left-[22%] right-[5%] sm:right-[8%] h-12 flex flex-col justify-between pointer-events-none opacity-60">
          <div className="w-full h-0.5 bg-blue-500 relative">
            <span className="absolute -top-3.5 right-1 text-[7px] sm:text-[8px] font-mono text-blue-400">MOSI</span>
          </div>
          <div className="w-full h-0.5 bg-green-500 relative">
            <span className="absolute -top-3.5 right-1 text-[7px] sm:text-[8px] font-mono text-green-400">MISO</span>
          </div>
          <div className="w-full h-0.5 bg-yellow-500 relative">
            <span className="absolute -top-3.5 right-1 text-[7px] sm:text-[8px] font-mono text-yellow-400">SCK</span>
          </div>
        </div>

        {/* Master (MCU) */}
        <div className="w-20 sm:w-28 h-36 sm:h-40 bg-purple-900 border border-purple-500 rounded-lg flex flex-col items-center justify-center z-10 shadow-[0_0_15px_rgba(168,85,247,0.3)] shrink-0">
          <Cpu className="w-6 h-6 sm:w-8 sm:h-8 text-purple-300 mb-1 sm:mb-2" />
          <span className="text-[11px] sm:text-xs font-bold text-white tracking-wide">Master</span>
          <div className="mt-2 sm:mt-4 flex flex-col gap-1 sm:gap-1.5 w-full px-2 sm:px-3">
            {[0, 1, 2].map((idx) => {
              const active = selectedSlave === idx;
              return (
                <div key={idx} className="flex justify-between items-center text-[8px] sm:text-[9px] text-gray-300 font-mono">
                  <span>CS{idx + 1}</span>
                  <div
                    className={`w-2 h-2 rounded-full transition-all ${
                      active
                        ? "bg-green-400 shadow-[0_0_6px_lime]"
                        : "bg-red-500"
                    }`}
                  />
                </div>
              );
            })}
          </div>
        </div>

        {/* Slaves Container */}
        <div className="flex-1 ml-2 sm:ml-4 flex justify-around items-center z-10 min-w-[200px]">
          {slaves.map((slave, index) => {
            const active = selectedSlave === index;
            return (
              <div key={index} className="flex flex-col items-center gap-1.5 sm:gap-2 relative">
                {/* CS Line (Vertical) */}
                <div
                  className={`absolute -top-8 sm:-top-10 bottom-[100%] w-0.5 transition-colors ${
                    active ? "bg-green-500" : "bg-gray-700"
                  }`}
                />

                {/* Toggle Switch */}
                <button
                  type="button"
                  onClick={() => handleToggleCS(index)}
                  className={`relative w-7 sm:w-8 h-3.5 sm:h-4 rounded-full transition-colors focus:outline-none cursor-pointer touch-manipulation ${
                    active ? "bg-green-600" : "bg-gray-700"
                  }`}
                >
                  <div
                    className={`absolute top-0.5 w-2.5 sm:w-3 h-2.5 sm:h-3 bg-white rounded-full transition-all ${
                      active ? "left-3.5 sm:left-4.5" : "left-0.5"
                    }`}
                  />
                </button>

                {/* Slave Box */}
                <div
                  className={`w-14 sm:w-22 h-20 sm:h-24 rounded flex flex-col items-center justify-center shadow-lg transition-all border p-1 ${
                    active
                      ? "border-green-500 bg-gray-800 shadow-green-500/20"
                      : "bg-gray-800 border-gray-600"
                  }`}
                >
                  <div className="scale-75 sm:scale-100 origin-center">
                    {renderSlaveIcon(slave.icon, active)}
                  </div>
                  <span className="text-[8px] sm:text-[10px] text-gray-300 mt-1 sm:mt-2 font-medium text-center leading-tight">
                    {slave.name}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Animated Flying Packets */}
        {isTransferring && selectedSlave !== null && (
          <>
            {/* MOSI packet: Master (left ~20%) -> Selected Slave (right ~45%, 65%, 85%) */}
            <div
              className="absolute w-2.5 sm:w-3 h-2.5 sm:h-3 bg-blue-400 rounded-full shadow-[0_0_8px_cyan] pointer-events-none z-20"
              style={{
                left: `${20 + (35 + selectedSlave * 20) * packetProgress}%`,
                top: "40%",
              }}
            />
            {/* MISO packet: Selected Slave -> Master (Full Duplex) */}
            <div
              className="absolute w-2.5 sm:w-3 h-2.5 sm:h-3 bg-green-400 rounded-full shadow-[0_0_8px_lime] pointer-events-none z-20"
              style={{
                left: `${(20 + (35 + selectedSlave * 20)) - (35 + selectedSlave * 20) * packetProgress}%`,
                top: "46%",
              }}
            />
          </>
        )}
      </div>

      {/* Controls & Feedback */}
      <div className="flex flex-col sm:flex-row justify-between items-center gap-3 pt-1">
        <div className={`text-sm ${feedback.color}`}>
          {feedback.msg}
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleReset}
            className="text-red-400 text-xs hover:text-red-300 underline font-medium"
          >
            Reset
          </button>
          {!verified ? (
            <button
              onClick={handleTransfer}
              disabled={isTransferring}
              className="bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-1.5 rounded text-sm font-bold transition-colors shadow-lg shadow-indigo-900/20 flex items-center gap-1.5"
            >
              🚀 Transfer Data
            </button>
          ) : (
            <Button onClick={onPass} className="bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs h-8">
              <CheckCircle2 className="size-4 mr-1.5" /> Complete Lab
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
