object BridgeForm: TBridgeForm
  Left = 320
  Top = 220
  Caption = 'AIDriveBridge - running'
  ClientHeight = 60
  ClientWidth = 300
  object Label1: TLabel
    Left = 12
    Top = 20
    Width = 270
    Height = 13
    Caption = 'Processed: 0'
  end
  object Timer1: TTimer
    Enabled = True
    Interval = 600
    OnTimer = Timer1Timer
  end
end
