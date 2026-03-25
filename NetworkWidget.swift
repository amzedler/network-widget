import Cocoa

// MARK: - Constants

let defaultPingInterval: TimeInterval = 60
let speedInterval: TimeInterval = 600
let pingHost = "8.8.8.8"
let pingCount = 4
let pingGood: Double = 50   // ms
let pingWarn: Double = 100
let maxPingHistory = 240     // scales with faster intervals
let maxSpeedHistory = 30     // ~5 hours at 10min

let pingIntervalOptions: [(String, TimeInterval)] = [
    ("1 second", 1),
    ("5 seconds", 5),
    ("10 seconds", 10),
    ("15 seconds", 15),
    ("30 seconds", 30),
    ("60 seconds", 60),
]

// MARK: - Chart Views

class PingChartView: NSView {
    var dataPoints: [(Date, Double)] = []

    override var isFlipped: Bool { true }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        guard let ctx = NSGraphicsContext.current?.cgContext else { return }

        let yLabelWidth: CGFloat = 36
        let leftMargin: CGFloat = 16
        let rightMargin: CGFloat = 16
        let topMargin: CGFloat = 26
        let chartLeft = leftMargin + yLabelWidth
        let chartWidth = bounds.width - chartLeft - rightMargin
        let chartHeight: CGFloat = 80
        let chartTop = topMargin
        let chartBottom = chartTop + chartHeight
        let chartRight = chartLeft + chartWidth

        // Title
        let title = NSAttributedString(string: "Ping", attributes: [
            .font: NSFont.systemFont(ofSize: 11, weight: .semibold),
            .foregroundColor: NSColor.secondaryLabelColor
        ])
        title.draw(at: NSPoint(x: leftMargin, y: 6))

        // Chart background
        let bgRect = CGRect(x: chartLeft, y: chartTop, width: chartWidth, height: chartHeight)
        let bgPath = CGPath(roundedRect: bgRect, cornerWidth: 6, cornerHeight: 6, transform: nil)
        ctx.saveGState()
        ctx.addPath(bgPath)
        ctx.clip()
        ctx.setFillColor(NSColor(white: 0, alpha: 0.04).cgColor)
        ctx.fill(bgRect)
        ctx.restoreGState()

        // Border
        ctx.setStrokeColor(NSColor.separatorColor.withAlphaComponent(0.15).cgColor)
        ctx.setLineWidth(0.5)
        ctx.addPath(bgPath)
        ctx.strokePath()

        // Determine Y scale from data
        let maxPing = max((dataPoints.map { $0.1 }.max() ?? 100) * 1.2, 50)
        let gridValues = yGridValues(maxVal: maxPing)

        // Grid lines + Y labels
        let yLabelAttr: [NSAttributedString.Key: Any] = [
            .font: NSFont.monospacedDigitSystemFont(ofSize: 9, weight: .regular),
            .foregroundColor: NSColor.tertiaryLabelColor
        ]
        ctx.setStrokeColor(NSColor.separatorColor.withAlphaComponent(0.12).cgColor)
        ctx.setLineWidth(0.5)
        ctx.setLineDash(phase: 0, lengths: [3, 3])
        for val in gridValues {
            let y = chartBottom - CGFloat(val / maxPing) * chartHeight
            if y > chartTop + 4 && y < chartBottom - 4 {
                ctx.move(to: CGPoint(x: chartLeft, y: y))
                ctx.addLine(to: CGPoint(x: chartRight, y: y))
            }
            let label = NSAttributedString(string: "\(Int(val))", attributes: yLabelAttr)
            let sz = label.size()
            label.draw(at: NSPoint(x: chartLeft - sz.width - 4, y: y - sz.height / 2))
        }
        ctx.strokePath()
        ctx.setLineDash(phase: 0, lengths: [])

        // Threshold lines
        drawThresholdLine(ctx: ctx, value: pingGood, maxVal: maxPing, chartLeft: chartLeft, chartRight: chartRight, chartTop: chartTop, chartBottom: chartBottom, chartHeight: chartHeight, color: NSColor(red: 0.2, green: 0.8, blue: 0.4, alpha: 0.4))
        drawThresholdLine(ctx: ctx, value: pingWarn, maxVal: maxPing, chartLeft: chartLeft, chartRight: chartRight, chartTop: chartTop, chartBottom: chartBottom, chartHeight: chartHeight, color: NSColor(red: 1.0, green: 0.75, blue: 0.0, alpha: 0.4))

        // Collecting data state
        guard dataPoints.count >= 2 else {
            let noData = NSAttributedString(string: "Collecting data\u{2026}", attributes: [
                .font: NSFont.systemFont(ofSize: 11),
                .foregroundColor: NSColor.tertiaryLabelColor
            ])
            let sz = noData.size()
            noData.draw(at: NSPoint(x: chartLeft + chartWidth / 2 - sz.width / 2, y: chartTop + chartHeight / 2 - sz.height / 2))
            drawTimeLabels(ctx: ctx, chartLeft: chartLeft, chartWidth: chartWidth, chartBottom: chartBottom, chartRight: chartRight)
            return
        }

        let now = Date()
        let windowSecs: Double = 2 * 60 * 60
        let startTime = now.addingTimeInterval(-windowSecs)
        let filtered = dataPoints.filter { $0.0 >= startTime }
        guard filtered.count >= 2 else {
            drawTimeLabels(ctx: ctx, chartLeft: chartLeft, chartWidth: chartWidth, chartBottom: chartBottom, chartRight: chartRight)
            return
        }

        // Clip for data drawing
        ctx.saveGState()
        ctx.addPath(bgPath)
        ctx.clip()

        let linePath = CGMutablePath()
        let fillPath = CGMutablePath()

        for (i, point) in filtered.enumerated() {
            let elapsed = point.0.timeIntervalSince(startTime)
            let x = chartLeft + CGFloat(elapsed / windowSecs) * chartWidth
            let val = min(max(point.1, 0), maxPing)
            let y = chartBottom - CGFloat(val / maxPing) * chartHeight

            if i == 0 {
                linePath.move(to: CGPoint(x: x, y: y))
                fillPath.move(to: CGPoint(x: x, y: chartBottom))
                fillPath.addLine(to: CGPoint(x: x, y: y))
            } else {
                linePath.addLine(to: CGPoint(x: x, y: y))
                fillPath.addLine(to: CGPoint(x: x, y: y))
            }
        }

        let lastX = chartLeft + CGFloat(filtered.last!.0.timeIntervalSince(startTime) / windowSecs) * chartWidth
        fillPath.addLine(to: CGPoint(x: lastX, y: chartBottom))
        fillPath.closeSubpath()

        // Color based on current ping
        let currentPing = filtered.last?.1 ?? 0
        let baseColor: NSColor
        if currentPing < pingGood {
            baseColor = NSColor(red: 0.25, green: 0.78, blue: 0.45, alpha: 1)
        } else if currentPing < pingWarn {
            baseColor = NSColor(red: 1.0, green: 0.72, blue: 0.1, alpha: 1)
        } else {
            baseColor = NSColor(red: 1.0, green: 0.3, blue: 0.3, alpha: 1)
        }

        // Gradient fill
        ctx.saveGState()
        ctx.addPath(fillPath)
        ctx.clip()
        let colors = [baseColor.withAlphaComponent(0.3).cgColor, baseColor.withAlphaComponent(0.02).cgColor]
        let gradient = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: colors as CFArray, locations: [0, 1])!
        ctx.drawLinearGradient(gradient, start: CGPoint(x: 0, y: chartTop), end: CGPoint(x: 0, y: chartBottom), options: [])
        ctx.restoreGState()

        // Line
        ctx.setStrokeColor(baseColor.cgColor)
        ctx.setLineWidth(1.5)
        ctx.setLineJoin(.round)
        ctx.setLineCap(.round)
        ctx.addPath(linePath)
        ctx.strokePath()

        // Dot at end
        let lastVal = min(max(filtered.last!.1, 0), maxPing)
        let dotY = chartBottom - CGFloat(lastVal / maxPing) * chartHeight
        ctx.setFillColor(baseColor.cgColor)
        ctx.fillEllipse(in: CGRect(x: lastX - 3, y: dotY - 3, width: 6, height: 6))
        ctx.setFillColor(NSColor.white.cgColor)
        ctx.fillEllipse(in: CGRect(x: lastX - 1.5, y: dotY - 1.5, width: 3, height: 3))

        ctx.restoreGState()
        drawTimeLabels(ctx: ctx, chartLeft: chartLeft, chartWidth: chartWidth, chartBottom: chartBottom, chartRight: chartRight)
    }

    func drawThresholdLine(ctx: CGContext, value: Double, maxVal: Double, chartLeft: CGFloat, chartRight: CGFloat, chartTop: CGFloat, chartBottom: CGFloat, chartHeight: CGFloat, color: NSColor) {
        guard value < maxVal else { return }
        let y = chartBottom - CGFloat(value / maxVal) * chartHeight
        ctx.saveGState()
        ctx.setStrokeColor(color.cgColor)
        ctx.setLineWidth(0.8)
        ctx.setLineDash(phase: 0, lengths: [4, 4])
        ctx.move(to: CGPoint(x: chartLeft, y: y))
        ctx.addLine(to: CGPoint(x: chartRight, y: y))
        ctx.strokePath()
        ctx.setLineDash(phase: 0, lengths: [])
        ctx.restoreGState()
    }

    func drawTimeLabels(ctx: CGContext, chartLeft: CGFloat, chartWidth: CGFloat, chartBottom: CGFloat, chartRight: CGFloat) {
        let now = Date()
        let windowSecs: Double = 2 * 60 * 60
        let startTime = now.addingTimeInterval(-windowSecs)

        let timeAttr: [NSAttributedString.Key: Any] = [
            .font: NSFont.monospacedDigitSystemFont(ofSize: 9, weight: .regular),
            .foregroundColor: NSColor.tertiaryLabelColor
        ]
        let formatter = DateFormatter()
        formatter.dateFormat = "h:mm"

        ctx.setStrokeColor(NSColor.separatorColor.withAlphaComponent(0.2).cgColor)
        ctx.setLineWidth(0.5)
        for mins in stride(from: 0, through: 120, by: 30) {
            let t = startTime.addingTimeInterval(Double(mins) * 60)
            let x = chartLeft + CGFloat(Double(mins) * 60 / windowSecs) * chartWidth
            ctx.move(to: CGPoint(x: x, y: chartBottom))
            ctx.addLine(to: CGPoint(x: x, y: chartBottom + 3))
            ctx.strokePath()
            let label = NSAttributedString(string: formatter.string(from: t), attributes: timeAttr)
            let lsz = label.size()
            let drawX = min(max(x - lsz.width / 2, chartLeft), chartRight - lsz.width)
            label.draw(at: NSPoint(x: drawX, y: chartBottom + 4))
        }
    }

    func yGridValues(maxVal: Double) -> [Double] {
        let step: Double
        if maxVal <= 50 { step = 10 }
        else if maxVal <= 100 { step = 25 }
        else if maxVal <= 250 { step = 50 }
        else { step = 100 }
        var vals: [Double] = []
        var v = step
        while v < maxVal {
            vals.append(v)
            v += step
        }
        return vals
    }
}


class SpeedChartView: NSView {
    var dataPoints: [(Date, Double, Double)] = []   // (time, dl, ul)

    override var isFlipped: Bool { true }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        guard let ctx = NSGraphicsContext.current?.cgContext else { return }

        let yLabelWidth: CGFloat = 36
        let leftMargin: CGFloat = 16
        let rightMargin: CGFloat = 16
        let topMargin: CGFloat = 26
        let chartLeft = leftMargin + yLabelWidth
        let chartWidth = bounds.width - chartLeft - rightMargin
        let chartHeight: CGFloat = 80
        let chartTop = topMargin
        let chartBottom = chartTop + chartHeight
        let chartRight = chartLeft + chartWidth

        // Title + legend
        let title = NSAttributedString(string: "Speed", attributes: [
            .font: NSFont.systemFont(ofSize: 11, weight: .semibold),
            .foregroundColor: NSColor.secondaryLabelColor
        ])
        title.draw(at: NSPoint(x: leftMargin, y: 6))

        let dlColor = NSColor(red: 0.25, green: 0.78, blue: 0.45, alpha: 1)
        let ulColor = NSColor(red: 0.4, green: 0.6, blue: 1.0, alpha: 1)

        // Legend dots
        let legendY: CGFloat = 8
        let dlLegend = NSMutableAttributedString()
        dlLegend.append(NSAttributedString(string: "● ", attributes: [.foregroundColor: dlColor, .font: NSFont.systemFont(ofSize: 8)]))
        dlLegend.append(NSAttributedString(string: "Down  ", attributes: [.font: NSFont.systemFont(ofSize: 9), .foregroundColor: NSColor.tertiaryLabelColor]))
        dlLegend.append(NSAttributedString(string: "● ", attributes: [.foregroundColor: ulColor, .font: NSFont.systemFont(ofSize: 8)]))
        dlLegend.append(NSAttributedString(string: "Up", attributes: [.font: NSFont.systemFont(ofSize: 9), .foregroundColor: NSColor.tertiaryLabelColor]))
        let legendSize = dlLegend.size()
        dlLegend.draw(at: NSPoint(x: chartRight - legendSize.width, y: legendY))

        // Chart background
        let bgRect = CGRect(x: chartLeft, y: chartTop, width: chartWidth, height: chartHeight)
        let bgPath = CGPath(roundedRect: bgRect, cornerWidth: 6, cornerHeight: 6, transform: nil)
        ctx.saveGState()
        ctx.addPath(bgPath)
        ctx.clip()
        ctx.setFillColor(NSColor(white: 0, alpha: 0.04).cgColor)
        ctx.fill(bgRect)
        ctx.restoreGState()

        ctx.setStrokeColor(NSColor.separatorColor.withAlphaComponent(0.15).cgColor)
        ctx.setLineWidth(0.5)
        ctx.addPath(bgPath)
        ctx.strokePath()

        let allSpeeds = dataPoints.flatMap { [$0.1, $0.2] }
        let maxSpeed = max((allSpeeds.max() ?? 100) * 1.2, 50)

        // Y grid
        let yLabelAttr: [NSAttributedString.Key: Any] = [
            .font: NSFont.monospacedDigitSystemFont(ofSize: 9, weight: .regular),
            .foregroundColor: NSColor.tertiaryLabelColor
        ]
        let gridVals = speedGridValues(maxVal: maxSpeed)
        ctx.setStrokeColor(NSColor.separatorColor.withAlphaComponent(0.12).cgColor)
        ctx.setLineWidth(0.5)
        ctx.setLineDash(phase: 0, lengths: [3, 3])
        for val in gridVals {
            let y = chartBottom - CGFloat(val / maxSpeed) * chartHeight
            if y > chartTop + 4 && y < chartBottom - 4 {
                ctx.move(to: CGPoint(x: chartLeft, y: y))
                ctx.addLine(to: CGPoint(x: chartRight, y: y))
            }
            let label = NSAttributedString(string: formatSpeedLabel(val), attributes: yLabelAttr)
            let sz = label.size()
            label.draw(at: NSPoint(x: chartLeft - sz.width - 4, y: y - sz.height / 2))
        }
        ctx.strokePath()
        ctx.setLineDash(phase: 0, lengths: [])

        guard dataPoints.count >= 2 else {
            let noData = NSAttributedString(string: "Collecting data\u{2026}", attributes: [
                .font: NSFont.systemFont(ofSize: 11),
                .foregroundColor: NSColor.tertiaryLabelColor
            ])
            let sz = noData.size()
            noData.draw(at: NSPoint(x: chartLeft + chartWidth / 2 - sz.width / 2, y: chartTop + chartHeight / 2 - sz.height / 2))
            drawTimeLabels(ctx: ctx, chartLeft: chartLeft, chartWidth: chartWidth, chartBottom: chartBottom, chartRight: chartRight)
            return
        }

        let now = Date()
        let windowSecs: Double = 2 * 60 * 60
        let startTime = now.addingTimeInterval(-windowSecs)
        let filtered = dataPoints.filter { $0.0 >= startTime }
        guard filtered.count >= 2 else {
            drawTimeLabels(ctx: ctx, chartLeft: chartLeft, chartWidth: chartWidth, chartBottom: chartBottom, chartRight: chartRight)
            return
        }

        ctx.saveGState()
        ctx.addPath(bgPath)
        ctx.clip()

        // Draw both lines
        for (seriesIdx, color) in [(0, dlColor), (1, ulColor)] {
            let linePath = CGMutablePath()
            let fillPath = CGMutablePath()

            for (i, point) in filtered.enumerated() {
                let elapsed = point.0.timeIntervalSince(startTime)
                let x = chartLeft + CGFloat(elapsed / windowSecs) * chartWidth
                let val = seriesIdx == 0 ? point.1 : point.2
                let clampedVal = min(max(val, 0), maxSpeed)
                let y = chartBottom - CGFloat(clampedVal / maxSpeed) * chartHeight

                if i == 0 {
                    linePath.move(to: CGPoint(x: x, y: y))
                    fillPath.move(to: CGPoint(x: x, y: chartBottom))
                    fillPath.addLine(to: CGPoint(x: x, y: y))
                } else {
                    linePath.addLine(to: CGPoint(x: x, y: y))
                    fillPath.addLine(to: CGPoint(x: x, y: y))
                }
            }

            let lastElapsed = filtered.last!.0.timeIntervalSince(startTime)
            let lastX = chartLeft + CGFloat(lastElapsed / windowSecs) * chartWidth
            fillPath.addLine(to: CGPoint(x: lastX, y: chartBottom))
            fillPath.closeSubpath()

            // Gradient fill
            ctx.saveGState()
            ctx.addPath(fillPath)
            ctx.clip()
            let colors = [color.withAlphaComponent(0.2).cgColor, color.withAlphaComponent(0.02).cgColor]
            let gradient = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: colors as CFArray, locations: [0, 1])!
            ctx.drawLinearGradient(gradient, start: CGPoint(x: 0, y: chartTop), end: CGPoint(x: 0, y: chartBottom), options: [])
            ctx.restoreGState()

            // Line
            ctx.setStrokeColor(color.cgColor)
            ctx.setLineWidth(1.5)
            ctx.setLineJoin(.round)
            ctx.setLineCap(.round)
            ctx.addPath(linePath)
            ctx.strokePath()

            // End dot
            let lastVal = seriesIdx == 0 ? filtered.last!.1 : filtered.last!.2
            let dotY = chartBottom - CGFloat(min(max(lastVal, 0), maxSpeed) / maxSpeed) * chartHeight
            ctx.setFillColor(color.cgColor)
            ctx.fillEllipse(in: CGRect(x: lastX - 3, y: dotY - 3, width: 6, height: 6))
            ctx.setFillColor(NSColor.white.cgColor)
            ctx.fillEllipse(in: CGRect(x: lastX - 1.5, y: dotY - 1.5, width: 3, height: 3))
        }

        ctx.restoreGState()
        drawTimeLabels(ctx: ctx, chartLeft: chartLeft, chartWidth: chartWidth, chartBottom: chartBottom, chartRight: chartRight)
    }

    func drawTimeLabels(ctx: CGContext, chartLeft: CGFloat, chartWidth: CGFloat, chartBottom: CGFloat, chartRight: CGFloat) {
        let now = Date()
        let windowSecs: Double = 2 * 60 * 60
        let startTime = now.addingTimeInterval(-windowSecs)

        let timeAttr: [NSAttributedString.Key: Any] = [
            .font: NSFont.monospacedDigitSystemFont(ofSize: 9, weight: .regular),
            .foregroundColor: NSColor.tertiaryLabelColor
        ]
        let formatter = DateFormatter()
        formatter.dateFormat = "h:mm"

        ctx.setStrokeColor(NSColor.separatorColor.withAlphaComponent(0.2).cgColor)
        ctx.setLineWidth(0.5)
        for mins in stride(from: 0, through: 120, by: 30) {
            let t = startTime.addingTimeInterval(Double(mins) * 60)
            let x = chartLeft + CGFloat(Double(mins) * 60 / windowSecs) * chartWidth
            ctx.move(to: CGPoint(x: x, y: chartBottom))
            ctx.addLine(to: CGPoint(x: x, y: chartBottom + 3))
            ctx.strokePath()
            let label = NSAttributedString(string: formatter.string(from: t), attributes: timeAttr)
            let lsz = label.size()
            let drawX = min(max(x - lsz.width / 2, chartLeft), chartRight - lsz.width)
            label.draw(at: NSPoint(x: drawX, y: chartBottom + 4))
        }
    }

    func speedGridValues(maxVal: Double) -> [Double] {
        let step: Double
        if maxVal <= 50 { step = 10 }
        else if maxVal <= 200 { step = 50 }
        else if maxVal <= 500 { step = 100 }
        else if maxVal <= 1000 { step = 250 }
        else { step = 500 }
        var vals: [Double] = []
        var v = step
        while v < maxVal {
            vals.append(v)
            v += step
        }
        return vals
    }

    func formatSpeedLabel(_ mbps: Double) -> String {
        if mbps >= 1000 { return String(format: "%.0fG", mbps / 1000) }
        return String(format: "%.0f", mbps)
    }
}


// MARK: - Network Measurement

func measurePing() -> Double? {
    let proc = Process()
    proc.executableURL = URL(fileURLWithPath: "/sbin/ping")
    proc.arguments = ["-c", "\(pingCount)", "-q", pingHost]
    let pipe = Pipe()
    proc.standardOutput = pipe
    proc.standardError = Pipe()

    do {
        try proc.run()
        proc.waitUntilExit()
    } catch { return nil }

    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    guard let output = String(data: data, encoding: .utf8) else { return nil }

    for line in output.components(separatedBy: "\n") {
        if line.contains("avg") || line.contains("min/avg") {
            let parts = line.components(separatedBy: "=")
            guard parts.count >= 2 else { continue }
            let vals = parts.last!.trimmingCharacters(in: .whitespaces).components(separatedBy: "/")
            if vals.count >= 2, let avg = Double(vals[1]) {
                return avg
            }
        }
    }
    return nil
}

func physicalInterface() -> String? {
    let proc = Process()
    proc.executableURL = URL(fileURLWithPath: "/usr/sbin/scutil")
    proc.arguments = ["--nwi"]
    let pipe = Pipe()
    proc.standardOutput = pipe
    proc.standardError = Pipe()

    do {
        try proc.run()
        proc.waitUntilExit()
    } catch { return nil }

    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    guard let output = String(data: data, encoding: .utf8) else { return nil }

    let regex = try? NSRegularExpression(pattern: #"\s+(en\d+)\s*:"#)
    for line in output.components(separatedBy: "\n") {
        if let match = regex?.firstMatch(in: line, range: NSRange(line.startIndex..., in: line)),
           let range = Range(match.range(at: 1), in: line) {
            return String(line[range])
        }
    }
    return nil
}

struct SpeedResult {
    let dl: Double  // Mbps
    let ul: Double  // Mbps
    let server: String
}

func measureSpeed() -> SpeedResult? {
    let proc = Process()
    proc.executableURL = URL(fileURLWithPath: "/usr/bin/networkQuality")
    var args = ["-c"]
    let iface = physicalInterface()
    if let iface = iface {
        args += ["-I", iface]
    }
    proc.arguments = args
    let pipe = Pipe()
    proc.standardOutput = pipe
    proc.standardError = Pipe()

    do {
        try proc.run()
        proc.waitUntilExit()
    } catch { return nil }

    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          let dlBits = json["dl_throughput"] as? Double,
          let ulBits = json["ul_throughput"] as? Double else { return nil }

    let label = iface ?? (json["interface_name"] as? String ?? "?")
    return SpeedResult(dl: dlBits / 1_000_000, ul: ulBits / 1_000_000, server: "Apple CDN (\(label))")
}

func formatSpeed(_ mbps: Double?) -> String {
    guard let mbps = mbps else { return "–" }
    if mbps >= 1000 { return String(format: "%.1f Gbps", mbps / 1000) }
    return String(format: "%.0f Mbps", mbps)
}


// MARK: - App Delegate

class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    var statusItem: NSStatusItem!
    var menu: NSMenu!
    var refreshTimer: Timer?

    // Cached data
    var cachedPingMs: Double?
    var cachedDlMbps: Double?
    var cachedUlMbps: Double?
    var cachedServer: String = "–"
    var speedRunning = false
    var speedNextTime: Date = .distantPast
    var pingRunning = false

    // Settings
    var pingInterval: TimeInterval = defaultPingInterval

    // History
    var pingHistory: [(Date, Double)] = []
    var speedHistory: [(Date, Double, Double)] = []   // (time, dl, ul)

    // Timing
    var nextPingTime: Date = .distantPast

    func applicationDidFinishLaunching(_ notification: Notification) {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        menu = NSMenu()
        menu.delegate = self
        statusItem.menu = menu

        updateTitle()

        // 1-second timer for title updates + scheduling background work
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            self?.tick()
        }
    }

    func tick() {
        let now = Date()

        // Kick off ping if needed (guard against overlap at fast intervals)
        if now >= nextPingTime && !pingRunning {
            pingRunning = true
            nextPingTime = now.addingTimeInterval(pingInterval)
            DispatchQueue.global(qos: .utility).async { [weak self] in
                let ping = measurePing()
                DispatchQueue.main.async {
                    self?.cachedPingMs = ping
                    self?.pingRunning = false
                    if let ping = ping {
                        self?.pingHistory.append((Date(), ping))
                        if let count = self?.pingHistory.count, count > maxPingHistory {
                            self?.pingHistory.removeFirst(count - maxPingHistory)
                        }
                    }
                }
            }
        }

        // Kick off speed test if needed
        if now >= speedNextTime && !speedRunning {
            speedRunning = true
            speedNextTime = now.addingTimeInterval(speedInterval)
            DispatchQueue.global(qos: .utility).async { [weak self] in
                let result = measureSpeed()
                DispatchQueue.main.async {
                    if let result = result {
                        self?.cachedDlMbps = result.dl
                        self?.cachedUlMbps = result.ul
                        self?.cachedServer = result.server
                        self?.speedHistory.append((Date(), result.dl, result.ul))
                        if let count = self?.speedHistory.count, count > maxSpeedHistory {
                            self?.speedHistory.removeFirst(count - maxSpeedHistory)
                        }
                    }
                    self?.speedRunning = false
                }
            }
        }

        updateTitle()
    }

    func updateTitle() {
        let dotColor: NSColor
        if let ping = cachedPingMs {
            if ping < pingGood {
                dotColor = NSColor(red: 0.2, green: 0.8, blue: 0.4, alpha: 1)
            } else if ping < pingWarn {
                dotColor = NSColor(red: 1.0, green: 0.75, blue: 0.0, alpha: 1)
            } else {
                dotColor = NSColor(red: 1.0, green: 0.25, blue: 0.25, alpha: 1)
            }
        } else {
            dotColor = NSColor.tertiaryLabelColor
        }

        let attrStr = NSMutableAttributedString()
        attrStr.append(NSAttributedString(string: "● ", attributes: [
            .foregroundColor: dotColor,
            .font: NSFont.systemFont(ofSize: 9)
        ]))

        let valueStr: String
        if let ping = cachedPingMs {
            valueStr = String(format: "%.0fms", ping)
        } else {
            valueStr = "–"
        }
        attrStr.append(NSAttributedString(string: valueStr, attributes: [
            .font: NSFont.monospacedDigitSystemFont(ofSize: 11, weight: .medium),
            .baselineOffset: 0.5
        ]))

        if let button = statusItem.button {
            button.attributedTitle = attrStr
        }
    }

    func menuWillOpen(_ menu: NSMenu) {
        menu.removeAllItems()
        menu.minimumWidth = 292

        // Header
        let header = NSMenuItem()
        header.attributedTitle = NSAttributedString(string: "Network", attributes: [
            .font: NSFont.systemFont(ofSize: 13, weight: .semibold)
        ])
        header.isEnabled = false
        menu.addItem(header)
        menu.addItem(NSMenuItem.separator())

        // Ping chart
        let pingChartItem = NSMenuItem()
        let pingChartView = PingChartView(frame: NSRect(x: 0, y: 0, width: 292, height: 130))
        pingChartView.dataPoints = pingHistory
        pingChartItem.view = pingChartView
        menu.addItem(pingChartItem)

        // Speed chart
        let speedChartItem = NSMenuItem()
        let speedChartView = SpeedChartView(frame: NSRect(x: 0, y: 0, width: 292, height: 130))
        speedChartView.dataPoints = speedHistory
        speedChartItem.view = speedChartView
        menu.addItem(speedChartItem)
        menu.addItem(NSMenuItem.separator())

        // Stats
        if let ping = cachedPingMs {
            addStatRow(menu: menu, label: "Ping", value: String(format: "%.1f ms", ping))
        } else {
            addStatRow(menu: menu, label: "Ping", value: "–")
        }
        addStatRow(menu: menu, label: "Download", value: formatSpeed(cachedDlMbps))
        addStatRow(menu: menu, label: "Upload", value: formatSpeed(cachedUlMbps))
        addStatRow(menu: menu, label: "Server", value: cachedServer, small: true)
        menu.addItem(NSMenuItem.separator())

        // Speed test status
        if speedRunning {
            let runningItem = NSMenuItem()
            runningItem.attributedTitle = NSAttributedString(string: "Running speed test\u{2026}", attributes: [
                .font: NSFont.systemFont(ofSize: 11),
                .foregroundColor: NSColor.secondaryLabelColor
            ])
            runningItem.isEnabled = false
            menu.addItem(runningItem)
        } else {
            let remaining = max(0, Int(speedNextTime.timeIntervalSinceNow))
            let mins = remaining / 60
            let secs = remaining % 60
            let countdownItem = NSMenuItem()
            countdownItem.attributedTitle = NSAttributedString(string: String(format: "Next speed test in: %dm %02ds", mins, secs), attributes: [
                .font: NSFont.monospacedDigitSystemFont(ofSize: 11, weight: .regular),
                .foregroundColor: NSColor.tertiaryLabelColor
            ])
            countdownItem.isEnabled = false
            menu.addItem(countdownItem)

            let runNow = NSMenuItem(title: "Run Speed Test Now", action: #selector(onRunSpeedTest), keyEquivalent: "")
            runNow.target = self
            menu.addItem(runNow)
        }

        menu.addItem(NSMenuItem.separator())

        // Speed history
        let validHistory = speedHistory.filter { $0.1 > 0 }
        if !validHistory.isEmpty {
            let histHeader = NSMenuItem()
            histHeader.attributedTitle = NSAttributedString(string: "Speed Test History (\(validHistory.count))", attributes: [
                .font: NSFont.systemFont(ofSize: 11, weight: .semibold),
                .foregroundColor: NSColor.secondaryLabelColor
            ])
            histHeader.isEnabled = false
            menu.addItem(histHeader)

            let formatter = DateFormatter()
            formatter.dateFormat = "H:mm"
            for entry in validHistory.reversed().prefix(10) {
                let ts = formatter.string(from: entry.0)
                addStatRow(menu: menu, label: ts, value: String(format: "\u{2193}%.0f  \u{2191}%.0f Mbps", entry.1, entry.2), small: true)
            }
            menu.addItem(NSMenuItem.separator())
        }

        // Ping frequency submenu
        let freqMenu = NSMenu()
        for (label, interval) in pingIntervalOptions {
            let item = NSMenuItem(title: label, action: #selector(onChangePingInterval(_:)), keyEquivalent: "")
            item.target = self
            item.tag = Int(interval)
            if Int(pingInterval) == Int(interval) {
                item.state = .on
            }
            freqMenu.addItem(item)
        }
        let freqItem = NSMenuItem()
        freqItem.attributedTitle = NSAttributedString(string: "Ping Frequency", attributes: [
            .font: NSFont.systemFont(ofSize: 11, weight: .semibold),
            .foregroundColor: NSColor.secondaryLabelColor
        ])
        freqItem.submenu = freqMenu
        menu.addItem(freqItem)
        menu.addItem(NSMenuItem.separator())

        let quit = NSMenuItem(title: "Quit", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        menu.addItem(quit)
    }

    @objc func onChangePingInterval(_ sender: NSMenuItem) {
        pingInterval = TimeInterval(sender.tag)
        // Trigger next ping soon so the new interval feels immediate
        nextPingTime = Date()
    }

    @objc func onRunSpeedTest() {
        guard !speedRunning else { return }
        speedRunning = true
        speedNextTime = Date().addingTimeInterval(speedInterval)
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let result = measureSpeed()
            DispatchQueue.main.async {
                if let result = result {
                    self?.cachedDlMbps = result.dl
                    self?.cachedUlMbps = result.ul
                    self?.cachedServer = result.server
                    self?.speedHistory.append((Date(), result.dl, result.ul))
                    if let count = self?.speedHistory.count, count > maxSpeedHistory {
                        self?.speedHistory.removeFirst(count - maxSpeedHistory)
                    }
                }
                self?.speedRunning = false
            }
        }
    }

    func addStatRow(menu: NSMenu, label: String, value: String, small: Bool = false) {
        let item = NSMenuItem()
        let fontSize: CGFloat = small ? 11 : 12
        let str = NSMutableAttributedString()
        str.append(NSAttributedString(string: label, attributes: [
            .font: NSFont.systemFont(ofSize: fontSize),
            .foregroundColor: small ? NSColor.tertiaryLabelColor : NSColor.labelColor
        ]))
        let para = NSMutableParagraphStyle()
        let tabStop = NSTextTab(textAlignment: .right, location: 260)
        para.tabStops = [tabStop]
        str.append(NSAttributedString(string: "\t" + value, attributes: [
            .font: NSFont.monospacedDigitSystemFont(ofSize: fontSize, weight: .medium),
            .foregroundColor: small ? NSColor.tertiaryLabelColor : NSColor.secondaryLabelColor,
            .paragraphStyle: para
        ]))
        item.attributedTitle = str
        item.isEnabled = false
        menu.addItem(item)
    }
}

// MARK: - Main

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
