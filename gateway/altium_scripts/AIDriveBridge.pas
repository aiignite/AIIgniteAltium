{ AIDriveBridge —— AIDriveAltium 网关的 Altium 驻留脚本 (DelphiScript)
  协议：行式文本协议 v1（与 gateway/altium_gateway/protocol.py 对应）
  用法：在 Altium 中 File > Open > Script Project 打开 AIDriveBridge.PrjSrc，
        运行 RunAIDriveBridge 过程，弹出窗口保持打开即可（勿最小化到关闭）。
  目录：%USERPROFILE%\Documents\AltiumBridge\{requests,responses}
        必须与 gateway 的 ALTIUM_BRIDGE_DIR 一致。 }

Interface

Const
    { 若与 gateway 配置不同请修改此处 }
    DEFAULT_BRIDGE_DIR_SUFFIX = 'AltiumBridge';
    POLL_INTERVAL_MS = 600;

Type
    TBridgeForm = Class(TForm)
        StatusLabel: TLabel;
        InfoLabel: TLabel;
        StartBtn: TButton;
        StopBtn: TButton;
        ProcessedLabel: TLabel;
        Timer1: TTimer;
        Procedure Timer1Timer(Sender: TObject);
        Procedure StartBtnClick(Sender: TObject);
        Procedure StopBtnClick(Sender: TObject);
        Procedure FormShow(Sender: TObject);
    End;

Var
    BridgeForm: TBridgeForm;
    ProcessedCount: Integer;
    BridgeDir: String;

Implementation

{$R *.dfm}

{ ---------- 基础工具 ---------- }

Function BridgeRequestsDir: String;
Begin
    Result := BridgeDir + '\requests';
End;

Function BridgeResponsesDir: String;
Begin
    Result := BridgeDir + '\responses';
End;

Procedure EnsureDir(const Dir: String);
Begin
    If Not DirectoryExists(Dir) Then
        ForceDirectories(Dir);
End;

Function SplitLine(const Line: String; const Sep: String): TStringList;
{ 按 Sep 切分一行（不使用 DelimitedText，避免引号语义干扰） }
Var
    Rest, Part: String;
    P: Integer;
    List: TStringList;
Begin
    List := TStringList.Create;
    Rest := Line;
    While Length(Rest) > 0 Do
    Begin
        P := Pos(Sep, Rest);
        If P > 0 Then
        Begin
            Part := Copy(Rest, 1, P - 1);
            Rest := Copy(Rest, P + Length(Sep), MaxInt);
        End
        Else
        Begin
            Part := Rest;
            Rest := '';
        End;
        List.Add(Part);
    End;
    Result := List;
End;

Function ValueOf(const Parts: TStringList; const Key: String; const Default: String): String;
Var
    I: Integer;
    P: TStringList;
    K, V: String;
Begin
    Result := Default;
    For I := 2 To Parts.Count - 1 Do
    Begin
        P := SplitLine(Parts[I], '=');
        If P.Count >= 2 Then
        Begin
            K := P[0];
            V := P[1];
            If SameText(K, Key) Then
                Result := V;
        End;
        P.Free;
    End;
End;

{ ---------- Altium 对象访问 ---------- }

Function CurrentPCBBoard: IPCB_Board;
Begin
    Result := PCBServer.GetCurrentPCBBoard;
End;

Function CurrentSchDocument: ISch_Document;
Begin
    Result := SchServer.GetCurrentSchDocument;
End;

Function CurrentDocumentKind: String;
Begin
    If CurrentPCBBoard <> Nil Then
        Result := 'PCB'
    Else If CurrentSchDocument <> Nil Then
        Result := 'SCH'
    Else
        Result := 'NONE';
End;

Function CurrentDocumentName: String;
Var
    Board: IPCB_Board;
    SchDoc: ISch_Document;
Begin
    Result := '';
    Board := CurrentPCBBoard;
    If Board <> Nil Then
        Result := ExtractFileName(Board.FileName)
    Else
    Begin
        SchDoc := CurrentSchDocument;
        If SchDoc <> Nil Then
            Result := ExtractFileName(SchDoc.DocumentName);
    End;
End;

{ ---------- 各操作实现（返回 RES 行）---------- }

Function OpPing(const Parts: TStringList): String;
Begin
    Result := 'RES|' + Parts[1] + '|OK|reply=PONG|server=AIDriveBridge|version=0.2';
End;

Function OpProjectInfo(const Parts: TStringList): String;
Var
    Workspace: IWorkspace;
    Project: IProject;
    Idx: Integer;
    Name, Path, Kind, DocName: String;
Begin
    Name := '(无打开工程)';
    Path := '';
    Try
        Workspace := GetWorkspace;
        If Workspace <> Nil Then
        Begin
            If Workspace.DM_FocusedProject <> Nil Then
            Begin
                Project := Workspace.DM_FocusedProject;
                Name := ExtractFileName(Project.DM_ProjectFullPath);
                Path := Project.DM_ProjectFullPath;
            End;
        End;
    Except
        Name := '(无法访问工作区)';
    End;
    Kind := CurrentDocumentKind;
    DocName := CurrentDocumentName;
    Result := 'RES|' + Parts[1] + '|OK|name=' + Name + '|path=' + Path
        + '|document_kind=' + Kind + '|document_name=' + DocName;
End;

Function OpSchComponents(const Parts: TStringList): String;
Var
    SchDoc: ISch_Document;
    Iterator: ISch_Iterator;
    Component: ISch_Component;
    Designator, LibRef, Comment: String;
    Count: Integer;
    Lines: TStringList;
Begin
    Lines := TStringList.Create;
    Count := 0;
    Try
        SchDoc := CurrentSchDocument;
        If SchDoc = Nil Then
        Begin
            Lines.Add('RES|' + Parts[1] + '|ERR|当前没有打开的原理图文档');
        End
        Else
        Begin
            Iterator := SchDoc.SchIterator_Create;
            Iterator.AddFilter_ObjectSet(eSchComponent);
            Component := Iterator.FirstSchObject;
            While Component <> Nil Do
            Begin
                Try
                    Designator := Component.Designator.Text;
                Except
                    Designator := '?';
                End;
                Try
                    LibRef := Component.LibReference;
                Except
                    LibRef := '';
                End;
                Try
                    Comment := Component.Comment.Text;
                Except
                    Try
                        Comment := Component.SourceComment;
                    Except
                        Comment := '';
                    End;
                End;
                Count := Count + 1;
                Lines.Add('RES|' + Parts[1] + '|ITEM|designator=' + Designator
                    + '|value=' + Comment + '|footprint=' + LibRef);
                Component := Iterator.NextSchObject;
            End;
            SchDoc.SchIterator_Destroy(Iterator);
            Lines.Add('RES|' + Parts[1] + '|OK|count=' + IntToStr(Count)
                + '|document=' + CurrentDocumentName);
        End;
    Except
        On E: Exception Do
            Lines.Add('RES|' + Parts[1] + '|ERR|' + E.Message);
    End;
    Result := Lines.Text;
    Lines.Free;
End;

Function OpSchNets(const Parts: TStringList): String;
Var
    SchDoc: ISch_Document;
    Iterator: ISch_Iterator;
    Obj: ISch_BasicObject;
    Names: TStringList;
    I, Idx, Count: Integer;
    NetName: String;
    Lines: TStringList;
Begin
    Names := TStringList.Create;
    Lines := TStringList.Create;
    Try
        SchDoc := CurrentSchDocument;
        If SchDoc = Nil Then
        Begin
            Lines.Add('RES|' + Parts[1] + '|ERR|当前没有打开的原理图文档');
        End
        Else
        Begin
            { 网络标签 }
            Iterator := SchDoc.SchIterator_Create;
            Iterator.AddFilter_ObjectSet(eNetLabel);
            Obj := Iterator.FirstSchObject;
            While Obj <> Nil Do
            Begin
                NetName := Obj.Text;
                Idx := Names.IndexOf(NetName);
                If Idx < 0 Then
                    Names.AddObject(NetName, TObject(1))
                Else
                    Names.Objects[Idx] := TObject(Integer(Names.Objects[Idx]) + 1);
                Obj := Iterator.NextSchObject;
            End;
            SchDoc.SchIterator_Destroy(Iterator);
            { 电源端口 }
            Iterator := SchDoc.SchIterator_Create;
            Iterator.AddFilter_ObjectSet(ePowerObject);
            Obj := Iterator.FirstSchObject;
            While Obj <> Nil Do
            Begin
                NetName := Obj.Text;
                Idx := Names.IndexOf(NetName);
                If Idx < 0 Then
                    Names.AddObject(NetName, TObject(1))
                Else
                    Names.Objects[Idx] := TObject(Integer(Names.Objects[Idx]) + 1);
                Obj := Iterator.NextSchObject;
            End;
            SchDoc.SchIterator_Destroy(Iterator);

            Count := 0;
            For I := 0 To Names.Count - 1 Do
            Begin
                Count := Count + 1;
                Lines.Add('RES|' + Parts[1] + '|ITEM|name=' + Names[I]
                    + '|count=' + IntToStr(Integer(Names.Objects[I])));
            End;
            Lines.Add('RES|' + Parts[1] + '|OK|count=' + IntToStr(Count)
                + '|document=' + CurrentDocumentName);
        End;
    Except
        On E: Exception Do
            Lines.Add('RES|' + Parts[1] + '|ERR|' + E.Message);
    End;
    Result := Lines.Text;
    Names.Free;
    Lines.Free;
End;

Function OpPcbComponents(const Parts: TStringList): String;
Var
    Board: IPCB_Board;
    Iterator: IPCB_GroupIterator;
    Component: IPCB_Component;
    Count: Integer;
    Lines: TStringList;
    Des, Foot, LayerName: String;
Begin
    Lines := TStringList.Create;
    Count := 0;
    Try
        Board := CurrentPCBBoard;
        If Board = Nil Then
        Begin
            Lines.Add('RES|' + Parts[1] + '|ERR|当前没有打开的 PCB 文档');
        End
        Else
        Begin
            Iterator := Board.BoardIterator_Create;
            Iterator.AddFilter_ObjectSet(MoComponent);
            Iterator.AddFilter_Method(eProcessAll);
            Component := Iterator.FirstPCBObject;
            While Component <> Nil Do
            Begin
                Try
                    Des := Component.Name.Text;
                Except
                    Des := '?';
                End;
                Try
                    Foot := Component.Footprint;
                Except
                    Foot := '';
                End;
                Try
                    LayerName := Board.LayerName(Component.Layer);
                Except
                    LayerName := '';
                End;
                Count := Count + 1;
                Lines.Add('RES|' + Parts[1] + '|ITEM|designator=' + Des
                    + '|footprint=' + Foot + '|layer=' + LayerName);
                Component := Iterator.NextPCBObject;
            End;
            Board.BoardIterator_Destroy(Iterator);
            Lines.Add('RES|' + Parts[1] + '|OK|count=' + IntToStr(Count)
                + '|document=' + CurrentDocumentName);
        End;
    Except
        On E: Exception Do
            Lines.Add('RES|' + Parts[1] + '|ERR|' + E.Message);
    End;
    Result := Lines.Text;
    Lines.Free;
End;

Function CountPcbObjects(Board: IPCB_Board; const ObjectSet: Integer): Integer;
Var
    Iterator: IPCB_GroupIterator;
    Obj: IPCB_Primitive;
    Count: Integer;
Begin
    Count := 0;
    Iterator := Board.BoardIterator_Create;
    Iterator.AddFilter_ObjectSet(ObjectSet);
    Iterator.AddFilter_Method(eProcessAll);
    Obj := Iterator.FirstPCBObject;
    While Obj <> Nil Do
    Begin
        Count := Count + 1;
        Obj := Iterator.NextPCBObject;
    End;
    Board.BoardIterator_Destroy(Iterator);
    Result := Count;
End;

Function OpPcbStats(const Parts: TStringList): String;
Var
    Board: IPCB_Board;
    TrackCount, PadCount, ViaCount, NetCount, CompCount: Integer;
    Outline: IPCB_BoardOutline;
    I: Integer;
    Pt: TCoordPoint;
    MinX, MinY, MaxX, MaxY: Integer;
    HaveOutline: Boolean;
    Lines: TStringList;
Begin
    Lines := TStringList.Create;
    Try
        Board := CurrentPCBBoard;
        If Board = Nil Then
        Begin
            Lines.Add('RES|' + Parts[1] + '|ERR|当前没有打开的 PCB 文档');
        End
        Else
        Begin
            TrackCount := CountPcbObjects(Board, MoTrack);
            PadCount := CountPcbObjects(Board, MoPad);
            ViaCount := CountPcbObjects(Board, MoVia);
            NetCount := CountPcbObjects(Board, MoNet);
            CompCount := CountPcbObjects(Board, MoComponent);
            MinX := 0; MinY := 0; MaxX := 0; MaxY := 0;
            HaveOutline := False;
            Try
                Outline := Board.BoardOutline;
                If (Outline <> Nil) And (Outline.VertexCount > 0) Then
                Begin
                    For I := 0 To Outline.VertexCount - 1 Do
                    Begin
                        Pt := Outline.Vertex[I];
                        If (Not HaveOutline) Or (Pt.X < MinX) Then MinX := Pt.X;
                        If (Not HaveOutline) Or (Pt.Y < MinY) Then MinY := Pt.Y;
                        If (Not HaveOutline) Or (Pt.X > MaxX) Then MaxX := Pt.X;
                        If (Not HaveOutline) Or (Pt.Y > MaxY) Then MaxY := Pt.Y;
                        HaveOutline := True;
                    End;
                End;
            Except
                HaveOutline := False;
            End;
            Lines.Add('RES|' + Parts[1] + '|OK|components=' + IntToStr(CompCount)
                + '|pads=' + IntToStr(PadCount)
                + '|tracks=' + IntToStr(TrackCount)
                + '|vias=' + IntToStr(ViaCount)
                + '|nets=' + IntToStr(NetCount)
                + '|left=' + IntToStr(MinX) + '|bottom=' + IntToStr(MinY)
                + '|right=' + IntToStr(MaxX) + '|top=' + IntToStr(MaxY)
                + '|unit=bm'
                + '|document=' + CurrentDocumentName);
        End;
    Except
        On E: Exception Do
            Lines.Add('RES|' + Parts[1] + '|ERR|' + E.Message);
    End;
    Result := Lines.Text;
    Lines.Free;
End;

Function OpStackup(const Parts: TStringList): String;
Var
    Board: IPCB_Board;
    Stack:	ILayerStack;
    I: Integer;
    Lines: TStringList;
    Count: Integer;
Begin
    Lines := TStringList.Create;
    Count := 0;
    Try
        Board := CurrentPCBBoard;
        If Board = Nil Then
        Begin
            Lines.Add('RES|' + Parts[1] + '|ERR|当前没有打开的 PCB 文档');
        End
        Else
        Begin
            Try
                Stack := Board.LayerStack;
                If Stack <> Nil Then
                Begin
                    For I := 0 To Stack.Count - 1 Do
                    Begin
                        Count := Count + 1;
                        Lines.Add('RES|' + Parts[1] + '|ITEM|name=' + Stack.LayerObjects[I].Name);
                    End;
                End;
            Except
                On E: Exception Do
                    Lines.Add('RES|' + Parts[1] + '|ERR|叠层读取失败: ' + E.Message);
            End;
            Lines.Add('RES|' + Parts[1] + '|OK|count=' + IntToStr(Count));
        End;
    Except
        On E: Exception Do
            Lines.Add('RES|' + Parts[1] + '|ERR|' + E.Message);
    End;
    Result := Lines.Text;
    Lines.Free;
End;

{ ---------- 截图（GDI 抓取 Altium 主窗口）---------- }

Function GetWindowDC(hWnd: LongWord): LongWord; StdCall; External 'user32.dll' Name 'GetWindowDC';
Function ReleaseDC(hWnd: LongWord; hDC: LongWord): LongInt; StdCall; External 'user32.dll' Name 'ReleaseDC';
Function GetWindowRect(hWnd: LongWord; Var Rect: TRect): LongInt; StdCall; External 'user32.dll' Name 'GetWindowRect';
Function CreateCompatibleDC(hDC: LongWord): LongWord; StdCall; External 'gdi32.dll' Name 'CreateCompatibleDC';
Function CreateCompatibleBitmap(hDC: LongWord; W: Integer; H: Integer): LongWord; StdCall; External 'gdi32.dll' Name 'CreateCompatibleBitmap';
Function SelectObject(hDC: LongWord; Obj: LongWord): LongWord; StdCall; External 'gdi32.dll' Name 'SelectObject';
Function DeleteObject(Obj: LongWord): LongInt; StdCall; External 'gdi32.dll' Name 'DeleteObject';
Function DeleteDC(hDC: LongWord): LongInt; StdCall; External 'gdi32.dll' Name 'DeleteDC';
Function BitBlt(destDC: LongWord; X: Integer; Y: Integer; W: Integer; H: Integer; srcDC: LongWord; XSrc: Integer; YSrc: Integer; Rop: LongWord): LongInt; StdCall; External 'gdi32.dll' Name 'BitBlt';

Function OpScreenshot(const Parts: TStringList): String;
Var
    Wnd: LongWord;
    DC, MemDC, Bmp: LongWord;
    Rect: TRect;
    W, H: Integer;
    Bitmap: TBitmap;
    ShotPath: String;
Begin
    Try
        Wnd := Application.MainForm.Handle;
        GetWindowRect(Wnd, Rect);
        W := Rect.Right - Rect.Left;
        H := Rect.Bottom - Rect.Top;
        If (W <= 0) Or (H <= 0) Then
        Begin
            Result := 'RES|' + Parts[1] + '|ERR|主窗口尺寸无效';
            Exit;
        End;
        DC := GetWindowDC(Wnd);
        MemDC := CreateCompatibleDC(DC);
        Bmp := CreateCompatibleBitmap(DC, W, H);
        SelectObject(MemDC, Bmp);
        BitBlt(MemDC, 0, 0, W, H, DC, 0, 0, SRCCOPY);
        Bitmap := TBitmap.Create;
        Bitmap.Handle := Bmp;
        ShotPath := BridgeResponsesDir + '\shot_' + Parts[1] + '.bmp';
        Bitmap.SaveToFile(ShotPath);
        Bitmap.Free;
        DeleteObject(Bmp);
        DeleteDC(MemDC);
        ReleaseDC(Wnd, DC);
        Result := 'RES|' + Parts[1] + '|OK|format=bmp|file=' + ShotPath + '|w=' + IntToStr(W) + '|h=' + IntToStr(H);
    Except
        On E: Exception Do
            Result := 'RES|' + Parts[1] + '|ERR|截图失败: ' + E.Message;
    End;
End;

{ ---------- 请求处理 ---------- }

Procedure ExecuteOp(const Parts: TStringList; Lines: TStringList);
Var
    Op: String;
Begin
    Op := Parts[1];
    If SameText(Op, 'ping') Then Lines.Add(OpPing(Parts))
    Else If SameText(Op, 'get_project_info') Then Lines.Add(OpProjectInfo(Parts))
    Else If SameText(Op, 'sch_components') Then Lines.Add(OpSchComponents(Parts))
    Else If SameText(Op, 'sch_nets') Then Lines.Add(OpSchNets(Parts))
    Else If SameText(Op, 'pcb_components') Then Lines.Add(OpPcbComponents(Parts))
    Else If SameText(Op, 'pcb_stats') Then Lines.Add(OpPcbStats(Parts))
    Else If SameText(Op, 'get_stackup') Then Lines.Add(OpStackup(Parts))
    Else If SameText(Op, 'take_screenshot') Then Lines.Add(OpScreenshot(Parts))
    Else Lines.Add('RES|' + Parts[1] + '|ERR|未知操作: ' + Op);
End;

Procedure ProcessOneRequest(const ReqPath: String);
Var
    Req, Out: TStringList;
    I, P: Integer;
    Line, ReqId: String;
    RespPath, ShotPath: String;
Begin
    Req := TStringList.Create;
    Out := TStringList.Create;
    Try
        Try
            Req.LoadFromFile(ReqPath);
        Except
            Exit;  // 可能正被 gateway 写入，下个 tick 重试
        End;
        ReqId := '';
        For I := 0 To Req.Count - 1 Do
        Begin
            Line := Trim(Req[I]);
            If Copy(UpperCase(Line), 1, 4) = 'END|' Then
                ReqId := Copy(Line, 5, MaxInt);
        End;
        If ReqId = '' Then Exit;

        For I := 0 To Req.Count - 1 Do
        Begin
            Line := Trim(Req[I]);
            If Copy(UpperCase(Line), 1, 3) = 'OP|' Then
            Begin
                Try
                    ExecuteOp(SplitLine(Line, '|'), Out);
                Except
                    On E: Exception Do
                        Out.Add('RES|' + IntToStr(I) + '|ERR|' + E.Message);
                End;
            End;
        End;
        Out.Add('END|' + ReqId);

        EnsureDir(BridgeResponsesDir);
        RespPath := BridgeResponsesDir + '\resp_' + ReqId + '.txt';
        Out.SaveToFile(RespPath);

        ProcessedCount := ProcessedCount + 1;
        ProcessedLabel.Caption := '已处理请求：' + IntToStr(ProcessedCount);

        { 截图 BMP 转交 gateway（gateway 转成 PNG 后删除）——无需在此处理 }
        DeleteFile(ReqPath);
    Finally
        Req.Free;
        Out.Free;
    End;
End;

Procedure ScanRequests;
Var
    SR: TSearchRec;
    ReqDir: String;
    Found: Integer;
    Guard: Integer;
Begin
    ReqDir := BridgeRequestsDir;
    If Not DirectoryExists(ReqDir) Then Exit;
    Guard := 0;
    Found := FindFirst(ReqDir + '\req_*.txt', faAnyFile, SR);
    While (Found = 0) And (Guard < 10) Do
    Begin
        ProcessOneRequest(ReqDir + '\' + SR.Name);
        Guard := Guard + 1;
        Found := FindNext(SR);
    End;
    FindClose(SR);
End;

{ ---------- 表单事件 ---------- }

Procedure TBridgeForm.Timer1Timer(Sender: TObject);
Begin
    Try
        ScanRequests;
    Except
        On E: Exception Do
            StatusLabel.Caption := '错误：' + E.Message;
    End;
End;

Procedure TBridgeForm.StartBtnClick(Sender: TObject);
Begin
    EnsureDir(BridgeRequestsDir);
    EnsureDir(BridgeResponsesDir);
    Timer1.Enabled := True;
    StatusLabel.Caption := '状态：轮询中（每 ' + IntToStr(POLL_INTERVAL_MS) + 'ms）';
End;

Procedure TBridgeForm.StopBtnClick(Sender: TObject);
Begin
    Timer1.Enabled := False;
    StatusLabel.Caption := '状态：已停止';
End;

Procedure TBridgeForm.FormShow(Sender: TObject);
Begin
    InfoLabel.Caption := '目录：' + BridgeDir;
    If Not Timer1.Enabled Then
        StartBtnClick(Self);
End;

{ ---------- 入口 ---------- }

Procedure RunAIDriveBridge;
Var
    Profile: String;
Begin
    ProcessedCount := 0;
    Profile := GetEnvironmentVariable('USERPROFILE');
    If Profile = '' Then
        Profile := 'C:\Users\Public';
    BridgeDir := Profile + '\Documents\' + DEFAULT_BRIDGE_DIR_SUFFIX;
    EnsureDir(BridgeRequestsDir);
    EnsureDir(BridgeResponsesDir);
    BridgeForm.Show;
End;
