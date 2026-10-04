declare module "seeso/easy-seeso"

declare module "webgazer" {
  const webgazer: {
    setRegression(name: string): typeof webgazer
    setTracker(name: string): typeof webgazer
    setGazeListener(listener: (data: { x: number; y: number } | null, elapsedTime: number) => void): typeof webgazer
    showVideoPreview(show: boolean): typeof webgazer
    showPredictionPoints(show: boolean): typeof webgazer
    showFaceOverlay(show: boolean): typeof webgazer
    showFaceFeedbackBox(show: boolean): typeof webgazer
    recordScreenPosition(x: number, y: number): void
    begin(): Promise<void>
    end(): void
    clearData(): void
  }
  export default webgazer
}
