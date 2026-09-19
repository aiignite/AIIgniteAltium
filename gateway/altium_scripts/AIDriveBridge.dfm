object BridgeForm: TBridgeForm
  Left = 320
  Top = 220
  Width = 380
  Height = 150
  BorderIcons = [biSystemMenu, biMinimize]
  Caption = 'AIDriveBridge - Altium 实时桥'
  Color = clBtnFace
  Font.Charset = DEFAULT_CHARSET
  Font.Size = 9
  Position = poScreenCenter
  LCLVersion = '1.0'
  object StatusLabel: TLabel
    Left = 12
    Top = 12
    Width = 340
    Height = 18
    Caption = '状态：初始化…'
  end
  object InfoLabel: TLabel
    Left = 12
    Top = 34
    Width = 340
    Height = 18
    Caption = '目录：(见 gateway 配置)'
  end
  object StartBtn: TButton
    Left = 12
    Top = 64
    Width = 90
    Height = 28
    Caption = '启动轮询'
    OnClick = StartBtnClick
  end
  object StopBtn: TButton
    Left = 110
    Top = 64
    Width = 90
    Height = 28
    Caption = '停止轮询'
    OnClick = StopBtnClick
  end
  object ProcessedLabel: TLabel
    Left = 212
    Top = 70
    Width = 140
    Height = 18
    Caption = '已处理请求：0'
  end
  object Timer1: TTimer
    Interval = 600
    Enabled = False
    OnTimer = Timer1Timer
  end
end
