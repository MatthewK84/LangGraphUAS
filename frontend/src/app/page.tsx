"use client";
import React, { useState } from "react";

interface PlanResult {
  is_viable: boolean;
  weather: {
    temperature_c: number;
    wind_speed_mps: number;
    wind_direction: number;
    humidity_percent: number;
    conditions: string;
  };
  calculations: {
    density_altitude_m: number;
    energy_required_wh: number;
    payload_margin_kg: number;
    safety_flags: {
      battery_viable: boolean;
      payload_within_limits: boolean;
      wind_within_limits: boolean;
      temperature_within_limits: boolean;
    };
  };
  report: string;
  thread_id: string; // ADDED
}

export default function MissionPlanner() {
  const [aircraftId, setAircraftId] = useState("DJI_M350");
  const [payloadId, setPayloadId] = useState("Zenmuse_H30T");
  const [distanceM, setDistanceM] = useState("5000");
  const [hoverTimeS, setHoverTimeS] = useState("600");
  const [targetAltitudeM, setTargetAltitudeM] = useState("120");
  const [elevationM, setElevationM] = useState("0");
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [currentThreadId, setCurrentThreadId] = useState<string | undefined>(undefined); // ADDED

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PlanResult | null>(null);

  const handleGetCurrentLocation = () => {
    if (!navigator.geolocation) {
      alert("Geolocation is not supported by your browser framework.");
      return;
    }
    setLoading(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLatitude(position.coords.latitude.toFixed(4));
        setLongitude(position.coords.longitude.toFixed(4));
        setLoading(false);
      },
      (error) => {
        setLoading(false);
        alert(`Location acquisition failed: ${error.message}`);
      }
    );
  };

  const handleAnalyzeMission = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!latitude || !longitude) {
      alert("Please specify Latitude and Longitude or click 'Know my Current Location'.");
      return;
    }

    setLoading(true);
    setResult(null);

    try {
      const response = await fetch("http://localhost:8000/api/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          aircraft_id: aircraftId,
          payload_id: payloadId,
          mission_params: {
            distance_m: parseFloat(distanceM),
            hover_time_s: parseFloat(hoverTimeS),
            target_altitude_m: parseFloat(targetAltitudeM),
            elevation_m: parseFloat(elevationM),
            latitude: parseFloat(latitude),
            longitude: parseFloat(longitude),
          },
          thread_id: currentThreadId // Pass memory pointer
        }),
      });

      if (!response.ok) throw new Error("Backend calculation failed.");
      const data = await response.json();
      setResult(data);
      setCurrentThreadId(data.thread_id); // Save memory pointer for next execution
    } catch (err) {
      alert("Error reaching the mission orchestration core.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-slate-900 text-slate-100 p-8 font-sans">
      <div className="max-w-6xl mx-auto space-y-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white">sUAS Intelligent Mission Planner</h1>
          <p className="text-slate-400 mt-1">Deterministic physics engines coupled with LangGraph orchestration.</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-1 bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-xl h-fit">
            <h2 className="text-xl font-semibold mb-4 text-white">Mission Configuration</h2>
            
            <form onSubmit={handleAnalyzeMission} className="space-y-4">
              <div>
                <label className="block text-xs font-medium uppercase tracking-wider text-slate-400 mb-1">Aircraft Platform</label>
                <select value={aircraftId} onChange={(e) => setAircraftId(e.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-sm text-white focus:outline-none focus:border-blue-500">
                  <option value="DJI_M350">DJI Matrice 350 RTK</option>
                  <option value="Mavic_3_Ent">DJI Mavic 3 Enterprise</option>
                  <option value="INVALID_AIRCRAFT">Force Validation Failure (Test Route)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium uppercase tracking-wider text-slate-400 mb-1">Payload System</label>
                <select value={payloadId} onChange={(e) => setPayloadId(e.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-sm text-white focus:outline-none focus:border-blue-500">
                  <option value="Zenmuse_H30T">Zenmuse H30T (Sensor)</option>
                  <option value="L1_LiDAR">Zenmuse L1 (LiDAR)</option>
                  <option value="None">No External Payload</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium uppercase tracking-wider text-slate-400 mb-1">Distance (m)</label>
                  <input type="number" value={distanceM} onChange={(e) => setDistanceM(e.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-sm text-white focus:outline-none" required />
                </div>
                <div>
                  <label className="block text-xs font-medium uppercase tracking-wider text-slate-400 mb-1">Hover Time (s)</label>
                  <input type="number" value={hoverTimeS} onChange={(e) => setHoverTimeS(e.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-sm text-white focus:outline-none" required />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium uppercase tracking-wider text-slate-400 mb-1">Target Alt (m)</label>
                  <input type="number" value={targetAltitudeM} onChange={(e) => setTargetAltitudeM(e.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-sm text-white focus:outline-none" required />
                </div>
                <div>
                  <label className="block text-xs font-medium uppercase tracking-wider text-slate-400 mb-1">Elevation (m)</label>
                  <input type="number" value={elevationM} onChange={(e) => setElevationM(e.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-sm text-white focus:outline-none" required />
                </div>
              </div>

              <div className="pt-2 border-t border-slate-700 space-y-3">
                <button type="button" onClick={handleGetCurrentLocation} className="w-full bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs font-medium py-2 rounded-lg transition-colors tracking-wide">
                  📍 Know my Current Location
                </button>
                
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium uppercase tracking-wider text-slate-400 mb-1">Latitude</label>
                    <input type="number" step="any" placeholder="0.0000" value={latitude} onChange={(e) => setLatitude(e.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-sm text-white focus:outline-none" required />
                  </div>
                  <div>
                    <label className="block text-xs font-medium uppercase tracking-wider text-slate-400 mb-1">Longitude</label>
                    <input type="number" step="any" placeholder="0.0000" value={longitude} onChange={(e) => setLongitude(e.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-sm text-white focus:outline-none" required />
                  </div>
                </div>
              </div>

              <button type="submit" disabled={loading} className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 text-white font-semibold py-3 rounded-lg text-sm mt-4 transition-colors shadow-lg">
                {loading ? "Processing Environment & Metrics..." : "Analyze Flight Feasibility"}
              </button>
            </form>
          </div>

          <div className="lg:col-span-2 space-y-6">
            {!result && !loading && (
              <div className="bg-slate-800 border border-dashed border-slate-700 rounded-xl p-12 text-center text-slate-500">
                Configure mission objectives and location metrics to view system dispatch parameters.
              </div>
            )}

            {loading && (
              <div className="bg-slate-800 border border-slate-700 rounded-xl p-12 text-center text-slate-400 animate-pulse">
                Running physics simulations and prompting AI copilot...
              </div>
            )}

            {result && (
              <>
                <div className={`p-4 rounded-xl border flex items-center justify-between shadow-md ${
                  result.is_viable ? "bg-emerald-950/40 border-emerald-800 text-emerald-400" : "bg-rose-950/40 border-rose-800 text-rose-400"
                }`}>
                  <div>
                    <span className="font-bold text-lg tracking-wide">
                      FLIGHT DISPATCH STATUS: {result.is_viable ? "CLEAR TO LAUNCH (GO)" : "MISSION DENIED (NO-GO)"}
                    </span>
                    <p className="text-xs mt-1 opacity-75 font-mono">Memory Thread ID: {result.thread_id}</p>
                  </div>
                </div>

                {Object.keys(result.weather).length > 0 && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 shadow-sm">
                      <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Live Environmental Telemetry</span>
                      <div className="mt-2 space-y-1 text-sm">
                        <p>Conditions: <span className="text-white font-medium">{result.weather.conditions}</span></p>
                        <p>Air Temperature: <span className="text-white font-medium">{result.weather.temperature_c}°C</span></p>
                        <p>Ambient Wind Velocity: <span className="text-white font-medium">{result.weather.wind_speed_mps} m/s</span></p>
                      </div>
                    </div>

                    {Object.keys(result.calculations).length > 0 && (
                        <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 shadow-sm">
                          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Aero-Engineering Performance</span>
                          <div className="mt-2 space-y-1 text-sm">
                            <p>Calculated Density Alt: <span className="text-white font-medium">{result.calculations.density_altitude_m} m</span></p>
                            <p>Required Power Budget: <span className="text-white font-medium">{result.calculations.energy_required_wh} Wh</span></p>
                            <p>Payload Structural Margin: <span className="text-white font-medium">{result.calculations.payload_margin_kg} kg</span></p>
                          </div>
                        </div>
                    )}
                  </div>
                )}

                <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 shadow-xl">
                  <h3 className="text-lg font-semibold border-b border-slate-700 pb-2 text-white mb-4">AI Safety Officer Report</h3>
                  <div className="prose prose-invert max-w-none text-slate-300 text-sm leading-relaxed whitespace-pre-wrap">
                    {result.report}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
