{ AIDriveBridge - Altium DelphiScript bridge for AIDriveAltium gateway.
  Protocol: line-based text v1 (gateway/altium_gateway/protocol.py).
  Form class TBridgeForm is auto-generated from AIDriveBridge.dfm.
  Run RunAIDriveBridge and keep the window open. }

Const
    BRIDGE_DIR = 'C:\Users\SEEYAO\Documents\AltiumBridge';
    MAX_INT = 2147483647;

Var
    ProcessedCount: Integer;
    BridgeDir: String;
    TickCount: Integer;

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
    If Not DirectoryExists(Dir) Then ForceDirectories(Dir);
End;

Procedure DbgMark(const Stage: String);
Var
    D: TStringList;
Begin
    Try
        D := TStringList.Create;
        D.Add(Stage);
        D.SaveToFile(BridgeDir + '\dbg_stage.txt');
        D.Free;
    Except
    End;
End;

Function SplitLine(const Line, Sep: String): TStringList;
Var
    Rest, Part: String;
    P: Integer;
Begin
    Result := TStringList.Create;
    Rest := Line;
    While Length(Rest) > 0 Do
    Begin
        P := Pos(Sep, Rest);
        If P > 0 Then
        Begin
            Part := Copy(Rest, 1, P - 1);
            Rest := Copy(Rest, P + Length(Sep), MAX_INT);
        End
        Else
        Begin
            Part := Rest;
            Rest := '';
        End;
        Result.Add(Part);
    End;
End;

{ ---------- Altium API helpers ---------- }

Function CurrentPCBBoard: IPCB_Board;
Var
    PcbServerObj: IPCB_ServerInterface;
Begin
    Result := Nil;
    Try
        PcbServerObj := PCBServer;
        If PcbServerObj <> Nil Then Result := PcbServerObj.GetCurrentPCBBoard;
    Except
    End;
End;

Function CurrentSchDocument: ISch_Document;
Var
    SchServerObj: ISch_ServerInterface;
Begin
    Result := Nil;
    Try
        SchServerObj := SchServer;
        If SchServerObj <> Nil Then Result := SchServerObj.GetCurrentSchDocument;
    Except
    End;
End;

Function CurrentDocumentName: String;
Var
    Board: IPCB_Board;
    SchDoc: ISch_Document;
Begin
    Result := '';
    Try
        Board := CurrentPCBBoard;
        If Board <> Nil Then
        Begin
            Result := ExtractFileName(Board.FileName);
            Exit;
        End;
    Except
    End;
    Try
        SchDoc := CurrentSchDocument;
        If SchDoc <> Nil Then Result := ExtractFileName(SchDoc.DocumentName);
    Except
    End;
End;

Function CountPcbObjects(Board: IPCB_Board; ObjectSet: Integer): Integer;
Var
    Iterator: IPCB_GroupIterator;
    Obj: IPCB_Primitive;
    Count: Integer;
Begin
    Count := 0;
    Try
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
    Except
    End;
    Result := Count;
End;

{ ---------- ops ---------- }

Procedure ProcessPing(const OpIndex: Integer; OutLines: TStringList);
Begin
    OutLines.Add('RES|' + IntToStr(OpIndex) + '|OK|reply=PONG|server=AIDriveBridge|version=1.2');
End;

Procedure ProcessProjectInfo(const OpIndex: Integer; OutLines: TStringList);
Var
    Workspace: IWorkspace;
    Project: IProject;
    Name, Path, Kind, DocName: String;
    Board: IPCB_Board;
    SchDoc: ISch_Document;
Begin
    Name := '(no project)';
    Path := '';
    Kind := 'NONE';
    DocName := '';
    Try
        Workspace := GetWorkspace;
        If Workspace <> Nil Then
        Begin
            Project := Workspace.DM_FocusedProject;
            If Project <> Nil Then
            Begin
                Path := Project.DM_ProjectFullPath;
                Name := ExtractFileName(Path);
            End;
        End;
    Except
    End;
    Try
        Board := CurrentPCBBoard;
        If Board <> Nil Then
        Begin
            Kind := 'PCB';
            DocName := ExtractFileName(Board.FileName);
        End
        Else
        Begin
            SchDoc := CurrentSchDocument;
            If SchDoc <> Nil Then
            Begin
                Kind := 'SCH';
                DocName := ExtractFileName(SchDoc.DocumentName);
            End;
        End;
    Except
    End;
    OutLines.Add('RES|' + IntToStr(OpIndex) + '|OK|name=' + Name + '|path=' + Path
        + '|document_kind=' + Kind + '|document_name=' + DocName);
End;

Procedure ProcessSchComponents(const OpIndex: Integer; OutLines: TStringList);
Var
    SchDoc: ISch_Document;
    Iterator: ISch_Iterator;
    Component: ISch_Component;
    Designator, LibRef, Comment: String;
    Count: Integer;
Begin
    Count := 0;
    Try
        SchDoc := CurrentSchDocument;
        If SchDoc = Nil Then
        Begin
            OutLines.Add('RES|' + IntToStr(OpIndex) + '|ERR|no schematic document');
            Exit;
        End;
        Iterator := SchDoc.SchIterator_Create;
        Iterator.AddFilter_ObjectSet(eSchComponent);
        Component := Iterator.FirstSchObject;
        While Component <> Nil Do
        Begin
            Designator := '';
            LibRef := '';
            Comment := '';
            Try
                Designator := Component.Designator.Text;
            Except
            End;
            Try
                LibRef := Component.LibReference;
            Except
            End;
            Try
                Comment := Component.Comment.Text;
            Except
            End;
            Count := Count + 1;
            OutLines.Add('RES|' + IntToStr(OpIndex) + '|ITEM|designator=' + Designator
                + '|value=' + Comment + '|footprint=' + LibRef);
            Component := Iterator.NextSchObject;
        End;
        SchDoc.SchIterator_Destroy(Iterator);
        OutLines.Add('RES|' + IntToStr(OpIndex) + '|OK|count=' + IntToStr(Count));
    Except
        OutLines.Add('RES|' + IntToStr(OpIndex) + '|ERR|sch_components failed');
    End;
End;

Procedure ProcessSchNets(const OpIndex: Integer; OutLines: TStringList);
Var
    SchDoc: ISch_Document;
    Iterator: ISch_Iterator;
    Obj: ISch_BasicObject;
    Names, Counts: TStringList;
    I, Idx, Count: Integer;
    NetName: String;
Begin
    Names := TStringList.Create;
    Counts := TStringList.Create;
    Count := 0;
    Try
        SchDoc := CurrentSchDocument;
        If SchDoc = Nil Then
        Begin
            OutLines.Add('RES|' + IntToStr(OpIndex) + '|ERR|no schematic document');
            Names.Free;
            Counts.Free;
            Exit;
        End;
        Iterator := SchDoc.SchIterator_Create;
        Iterator.AddFilter_ObjectSet(eNetLabel);
        Obj := Iterator.FirstSchObject;
        While Obj <> Nil Do
        Begin
            NetName := '';
            Try
                NetName := Obj.Text;
            Except
            End;
            If NetName <> '' Then
            Begin
                Idx := Names.IndexOf(NetName);
                If Idx < 0 Then
                Begin
                    Names.Add(NetName);
                    Counts.Add('1');
                End
                Else
                Begin
                    Counts[Idx] := IntToStr(StrToInt(Counts[Idx]) + 1);
                End;
            End;
            Obj := Iterator.NextSchObject;
        End;
        SchDoc.SchIterator_Destroy(Iterator);
        Iterator := SchDoc.SchIterator_Create;
        Iterator.AddFilter_ObjectSet(ePowerObject);
        Obj := Iterator.FirstSchObject;
        While Obj <> Nil Do
        Begin
            NetName := '';
            Try
                NetName := Obj.Text;
            Except
            End;
            If NetName <> '' Then
            Begin
                Idx := Names.IndexOf(NetName);
                If Idx < 0 Then
                Begin
                    Names.Add(NetName);
                    Counts.Add('1');
                End
                Else
                Begin
                    Counts[Idx] := IntToStr(StrToInt(Counts[Idx]) + 1);
                End;
            End;
            Obj := Iterator.NextSchObject;
        End;
        SchDoc.SchIterator_Destroy(Iterator);
        For I := 0 To Names.Count - 1 Do
        Begin
            Count := Count + 1;
            OutLines.Add('RES|' + IntToStr(OpIndex) + '|ITEM|name=' + Names[I]
                + '|count=' + Counts[I]);
        End;
        OutLines.Add('RES|' + IntToStr(OpIndex) + '|OK|count=' + IntToStr(Count));
    Except
        OutLines.Add('RES|' + IntToStr(OpIndex) + '|ERR|sch_nets failed');
    End;
    Names.Free;
    Counts.Free;
End;

Procedure ProcessPcbComponents(const OpIndex: Integer; OutLines: TStringList);
Var
    Board: IPCB_Board;
    Iterator: IPCB_GroupIterator;
    Component: IPCB_Component;
    Count: Integer;
    Des, Foot, LayerName: String;
    XLoc, YLoc, Rot: Integer;
Begin
    Count := 0;
    Try
        Board := CurrentPCBBoard;
        If Board = Nil Then
        Begin
            OutLines.Add('RES|' + IntToStr(OpIndex) + '|ERR|no pcb document');
            Exit;
        End;
        Iterator := Board.BoardIterator_Create;
        Iterator.AddFilter_ObjectSet(1 shl Ord(eComponentObject));
        Iterator.AddFilter_Method(eProcessAll);
        Component := Iterator.FirstPCBObject;
        While Component <> Nil Do
        Begin
            Des := '';
            Foot := '';
            LayerName := '';
            XLoc := 0;
            YLoc := 0;
            Rot := 0;
            Try
                Des := Component.Name.Text;
            Except
            End;
            Try
                Foot := Component.Footprint;
            Except
            End;
            Try
                LayerName := Board.LayerName(Component.Layer);
            Except
            End;
            Try
                XLoc := Component.XLocation;
                YLoc := Component.YLocation;
            Except
            End;
            Try
                Rot := Component.Rotation;
            Except
            End;
            Count := Count + 1;
            OutLines.Add('RES|' + IntToStr(OpIndex) + '|ITEM|designator=' + Des
                + '|footprint=' + Foot + '|layer=' + LayerName
                + '|x=' + IntToStr(XLoc div 10000) + '|y=' + IntToStr(YLoc div 10000)
                + '|rotation=' + IntToStr(Rot div 10));
            Component := Iterator.NextPCBObject;
        End;
        Board.BoardIterator_Destroy(Iterator);
        OutLines.Add('RES|' + IntToStr(OpIndex) + '|OK|count=' + IntToStr(Count));
    Except
        OutLines.Add('RES|' + IntToStr(OpIndex) + '|ERR|pcb_components failed');
    End;
End;

Procedure ProcessPcbStats(const OpIndex: Integer; OutLines: TStringList);
Var
    Board: IPCB_Board;
    TrackCount, PadCount, ViaCount, NetCount, CompCount, LayerCount: Integer;
    Outline: IPCB_BoardOutline;
    OutlineIter: IPCB_GroupIterator;
    MinX, MinY, MaxX, MaxY: Integer;
    HaveOutline: Boolean;
    Stack: ILayerStack;
Begin
    MinX := 0; MinY := 0; MaxX := 0; MaxY := 0;
    HaveOutline := False;
    LayerCount := 0;
    Try
        Board := CurrentPCBBoard;
        If Board = Nil Then
        Begin
            OutLines.Add('RES|' + IntToStr(OpIndex) + '|ERR|no pcb document');
            Exit;
        End;
        TrackCount := CountPcbObjects(Board, 1 shl Ord(eTrackObject));
        PadCount := CountPcbObjects(Board, 1 shl Ord(ePadObject));
        ViaCount := CountPcbObjects(Board, 1 shl Ord(eViaObject));
        NetCount := CountPcbObjects(Board, 1 shl Ord(eNetObject));
        CompCount := CountPcbObjects(Board, 1 shl Ord(eComponentObject));
        Try
            OutlineIter := Board.BoardIterator_Create;
            OutlineIter.AddFilter_ObjectSet(1 shl Ord(eBoardOutlineObject));
            OutlineIter.AddFilter_Method(eProcessAll);
            Outline := OutlineIter.FirstPCBObject;
            While Outline <> Nil Do
            Begin
                MinX := Outline.X1;
                MinY := Outline.Y1;
                MaxX := Outline.X2;
                MaxY := Outline.Y2;
                HaveOutline := True;
                Outline := OutlineIter.NextPCBObject;
            End;
            Board.BoardIterator_Destroy(OutlineIter);
        Except
        End;
        Try
            Stack := Board.LayerStack;
            If Stack <> Nil Then LayerCount := Stack.Count;
        Except
        End;
        OutLines.Add('RES|' + IntToStr(OpIndex) + '|OK|components=' + IntToStr(CompCount)
            + '|pads=' + IntToStr(PadCount)
            + '|tracks=' + IntToStr(TrackCount)
            + '|vias=' + IntToStr(ViaCount)
            + '|nets=' + IntToStr(NetCount)
            + '|layers=' + IntToStr(LayerCount)
            + '|left=' + IntToStr(MinX) + '|bottom=' + IntToStr(MinY)
            + '|right=' + IntToStr(MaxX) + '|top=' + IntToStr(MaxY)
            + '|document=' + CurrentDocumentName);
    Except
        OutLines.Add('RES|' + IntToStr(OpIndex) + '|ERR|pcb_stats failed');
    End;
End;

Procedure ProcessStackup(const OpIndex: Integer; OutLines: TStringList);
Var
    Board: IPCB_Board;
    Stack: ILayerStack;
    I, Count: Integer;
Begin
    Count := 0;
    Try
        Board := CurrentPCBBoard;
        If Board = Nil Then
        Begin
            OutLines.Add('RES|' + IntToStr(OpIndex) + '|ERR|no pcb document');
            Exit;
        End;
        Stack := Board.LayerStack;
        If Stack <> Nil Then
        Begin
            For I := 0 To Stack.Count - 1 Do
            Begin
                Count := Count + 1;
                OutLines.Add('RES|' + IntToStr(OpIndex) + '|ITEM|name=' + Stack.LayerObjects[I].Name);
            End;
        End;
        OutLines.Add('RES|' + IntToStr(OpIndex) + '|OK|count=' + IntToStr(Count));
    Except
        OutLines.Add('RES|' + IntToStr(OpIndex) + '|ERR|stackup failed');
    End;
End;

Procedure ProcessScreenshot(const OpIndex: Integer; OutLines: TStringList);
Begin
    OutLines.Add('RES|' + IntToStr(OpIndex) + '|ERR|take_screenshot not supported by DelphiScript');
End;

{ ---------- write ops ---------- }

Function GetParam(Params: TStringList; const Name: String): String;
Var
    I, P: Integer;
Begin
    Result := '';
    If Params = Nil Then Exit;
    For I := 0 To Params.Count - 1 Do
    Begin
        P := Pos(Name + '=', Params[I]);
        If P = 1 Then
        Begin
            Result := Copy(Params[I], Length(Name) + 2, MAX_INT);
            Exit;
        End;
    End;
End;

Function MilsToTUnits(const Mils: Integer): Integer;
Begin
    Result := Mils * 10000;
End;

Procedure ProcessPcbHighlightNet(const OpIndex: Integer; Params: TStringList; OutLines: TStringList);
Var
    Board: IPCB_Board;
    Iterator: IPCB_GroupIterator;
    Obj: IPCB_Primitive;
    Net: IPCB_Net;
    NetName, ModeStr: String;
    DoHighlight: Boolean;
    Count: Integer;
Begin
    Count := 0;
    Try
        Board := CurrentPCBBoard;
        If Board = Nil Then
        Begin
            OutLines.Add('RES|' + IntToStr(OpIndex) + '|ERR|no pcb document');
            Exit;
        End;
        NetName := GetParam(Params, 'net');
        If NetName = '' Then
        Begin
            OutLines.Add('RES|' + IntToStr(OpIndex) + '|ERR|missing net param');
            Exit;
        End;
        ModeStr := GetParam(Params, 'mode');
        DoHighlight := True;
        If ModeStr = '0' Then DoHighlight := False;
        PCBServer.PreProcess(Board);
        Iterator := Board.BoardIterator_Create;
        Iterator.AddFilter_Method(eProcessAll);
        Obj := Iterator.FirstPCBObject;
        While Obj <> Nil Do
        Begin
            Net := Nil;
            Try
                Net := Obj.Net;
            Except
            End;
            If Net <> Nil Then
            Begin
                Try
                    If Net.Name = NetName Then
                    Begin
                        If DoHighlight Then Board.HighlightObject(Obj)
                        Else Board.DeHighlightObject(Obj);
                        Count := Count + 1;
                    End;
                Except
                End;
            End;
            Obj := Iterator.NextPCBObject;
        End;
        Board.BoardIterator_Destroy(Iterator);
        PCBServer.PostProcess(Board);
        OutLines.Add('RES|' + IntToStr(OpIndex) + '|OK|count=' + IntToStr(Count)
            + '|net=' + NetName + '|mode=' + ModeStr);
    Except
        OutLines.Add('RES|' + IntToStr(OpIndex) + '|ERR|pcb_highlight_net failed');
    End;
End;

Procedure ProcessPcbMoveComponent(const OpIndex: Integer; Params: TStringList; OutLines: TStringList);
Var
    Board: IPCB_Board;
    Iterator: IPCB_GroupIterator;
    Comp: IPCB_Component;
    Designator, Des, XStr, YStr: String;
    X, Y, OldX, OldY: Integer;
    Found: Boolean;
Begin
    Found := False;
    Try
        Board := CurrentPCBBoard;
        If Board = Nil Then
        Begin
            OutLines.Add('RES|' + IntToStr(OpIndex) + '|ERR|no pcb document');
            Exit;
        End;
        Designator := GetParam(Params, 'designator');
        XStr := GetParam(Params, 'x');
        YStr := GetParam(Params, 'y');
        If (Designator = '') Or (XStr = '') Or (YStr = '') Then
        Begin
            OutLines.Add('RES|' + IntToStr(OpIndex) + '|ERR|missing designator/x/y params');
            Exit;
        End;
        X := StrToInt(XStr);
        Y := StrToInt(YStr);
        Iterator := Board.BoardIterator_Create;
        Iterator.AddFilter_ObjectSet(1 shl Ord(eComponentObject));
        Iterator.AddFilter_Method(eProcessAll);
        Comp := Iterator.FirstPCBObject;
        While (Comp <> Nil) And (Not Found) Do
        Begin
            Des := '';
            Try
                Des := Comp.Name.Text;
            Except
            End;
            If Des = Designator Then
            Begin
                OldX := 0;
                OldY := 0;
                Try
                    OldX := Comp.XLocation div 10000;
                    OldY := Comp.YLocation div 10000;
                Except
                End;
                PCBServer.PreProcess(Board);
                Try
                    Comp.MoveToLocation(MilsToTUnits(X), MilsToTUnits(Y));
                Except
                    Comp.XLocation := MilsToTUnits(X);
                    Comp.YLocation := MilsToTUnits(Y);
                End;
                PCBServer.PostProcess(Board);
                Found := True;
            End;
            Comp := Iterator.NextPCBObject;
        End;
        Board.BoardIterator_Destroy(Iterator);
        If Not Found Then
            OutLines.Add('RES|' + IntToStr(OpIndex) + '|ERR|component not found: ' + Designator)
        Else
            OutLines.Add('RES|' + IntToStr(OpIndex) + '|OK|designator=' + Designator
                + '|x=' + IntToStr(X) + '|y=' + IntToStr(Y)
                + '|old_x=' + IntToStr(OldX) + '|old_y=' + IntToStr(OldY));
    Except
        OutLines.Add('RES|' + IntToStr(OpIndex) + '|ERR|pcb_move_component failed');
    End;
End;

Procedure ProcessPcbRotateComponent(const OpIndex: Integer; Params: TStringList; OutLines: TStringList);
Var
    Board: IPCB_Board;
    Iterator: IPCB_GroupIterator;
    Comp: IPCB_Component;
    Designator, Des, RotStr: String;
    Rot, OldRot: Integer;
    Found: Boolean;
Begin
    Found := False;
    Try
        Board := CurrentPCBBoard;
        If Board = Nil Then
        Begin
            OutLines.Add('RES|' + IntToStr(OpIndex) + '|ERR|no pcb document');
            Exit;
        End;
        Designator := GetParam(Params, 'designator');
        RotStr := GetParam(Params, 'rotation');
        If (Designator = '') Or (RotStr = '') Then
        Begin
            OutLines.Add('RES|' + IntToStr(OpIndex) + '|ERR|missing designator/rotation params');
            Exit;
        End;
        Rot := StrToInt(RotStr);
        Iterator := Board.BoardIterator_Create;
        Iterator.AddFilter_ObjectSet(1 shl Ord(eComponentObject));
        Iterator.AddFilter_Method(eProcessAll);
        Comp := Iterator.FirstPCBObject;
        While (Comp <> Nil) And (Not Found) Do
        Begin
            Des := '';
            Try
                Des := Comp.Name.Text;
            Except
            End;
            If Des = Designator Then
            Begin
                OldRot := 0;
                Try
                    OldRot := Comp.Rotation div 10;
                Except
                End;
                PCBServer.PreProcess(Board);
                Comp.Rotation := Rot * 10;
                PCBServer.PostProcess(Board);
                Found := True;
            End;
            Comp := Iterator.NextPCBObject;
        End;
        Board.BoardIterator_Destroy(Iterator);
        If Not Found Then
            OutLines.Add('RES|' + IntToStr(OpIndex) + '|ERR|component not found: ' + Designator)
        Else
            OutLines.Add('RES|' + IntToStr(OpIndex) + '|OK|designator=' + Designator
                + '|rotation=' + IntToStr(Rot)
                + '|old_rotation=' + IntToStr(OldRot));
    Except
        OutLines.Add('RES|' + IntToStr(OpIndex) + '|ERR|pcb_rotate_component failed');
    End;
End;

Procedure ExecuteOp(const Op: String; const OpIndex: Integer; Params: TStringList; OutLines: TStringList);
Begin
    If SameText(Op, 'ping') Then ProcessPing(OpIndex, OutLines)
    Else If SameText(Op, 'get_project_info') Then ProcessProjectInfo(OpIndex, OutLines)
    Else If SameText(Op, 'sch_components') Then ProcessSchComponents(OpIndex, OutLines)
    Else If SameText(Op, 'sch_nets') Then ProcessSchNets(OpIndex, OutLines)
    Else If SameText(Op, 'pcb_components') Then ProcessPcbComponents(OpIndex, OutLines)
    Else If SameText(Op, 'pcb_stats') Then ProcessPcbStats(OpIndex, OutLines)
    Else If SameText(Op, 'get_stackup') Then ProcessStackup(OpIndex, OutLines)
    Else If SameText(Op, 'take_screenshot') Then ProcessScreenshot(OpIndex, OutLines)
    Else If SameText(Op, 'pcb_highlight_net') Then ProcessPcbHighlightNet(OpIndex, Params, OutLines)
    Else If SameText(Op, 'pcb_move_component') Then ProcessPcbMoveComponent(OpIndex, Params, OutLines)
    Else If SameText(Op, 'pcb_rotate_component') Then ProcessPcbRotateComponent(OpIndex, Params, OutLines)
    Else OutLines.Add('RES|' + IntToStr(OpIndex) + '|ERR|unknown op: ' + Op);
End;

Procedure ExecuteRequest(const ReqPath, RespPath: String);
Var
    Req, OutLines: TStringList;
    I, J, OpIndex: Integer;
    Line, ReqId, Op: String;
    Parts, Params: TStringList;
Begin
    Req := TStringList.Create;
    OutLines := TStringList.Create;
    Try
        Try
            Req.LoadFromFile(ReqPath);
        Except
            Exit;
        End;
        ReqId := '';
        For I := 0 To Req.Count - 1 Do
        Begin
            Line := Trim(Req[I]);
            If Copy(UpperCase(Line), 1, 4) = 'END|' Then
                ReqId := Copy(Line, 5, MAX_INT);
        End;
        If ReqId = '' Then Exit;

        OpIndex := 0;
        For I := 0 To Req.Count - 1 Do
        Begin
            Line := Trim(Req[I]);
            If Copy(UpperCase(Line), 1, 3) = 'OP|' Then
            Begin
                Op := '';
                Params := Nil;
                Try
                    Parts := SplitLine(Line, '|');
                    If Parts.Count >= 2 Then
                    Begin
                        Op := Parts[1];
                        Params := TStringList.Create;
                        For J := 2 To Parts.Count - 1 Do Params.Add(Parts[J]);
                    End;
                    Parts.Free;
                Except
                End;
                If Op <> '' Then
                Begin
                    DbgMark('op-start:' + Op + '#' + IntToStr(OpIndex));
                    ExecuteOp(Op, OpIndex, Params, OutLines);
                    DbgMark('op-done:' + Op + '#' + IntToStr(OpIndex));
                    OpIndex := OpIndex + 1;
                End;
                If Params <> Nil Then Params.Free;
            End;
        End;
        OutLines.Add('END|' + ReqId);

        EnsureDir(BridgeResponsesDir);
        OutLines.SaveToFile(RespPath);

        ProcessedCount := ProcessedCount + 1;
        DeleteFile(ReqPath);
    Finally
        Req.Free;
        OutLines.Free;
    End;
End;

Procedure ScanRequests;
Var
    ReqPath, RespPath: String;
Begin
    ReqPath := BridgeRequestsDir + '\request.txt';
    RespPath := BridgeResponsesDir + '\response.txt';
    If FileExists(ReqPath) Then ExecuteRequest(ReqPath, RespPath);
End;

Procedure TBridgeForm.Timer1Timer(Sender: TObject);
Begin
    TickCount := TickCount + 1;
    If (TickCount Mod 50) = 1 Then DbgMark('tick#' + IntToStr(TickCount));
    Try
        ScanRequests;
    Except
    End;
    Try
        BridgeForm.Label1.Caption := 'Processed: ' + IntToStr(ProcessedCount);
    Except
    End;
End;

Procedure RunAIDriveBridge;
Var
    Diag: TStringList;
Begin
    ProcessedCount := 0;
    TickCount := 0;
    BridgeDir := BRIDGE_DIR;
    EnsureDir(BridgeDir);
    EnsureDir(BridgeRequestsDir);
    EnsureDir(BridgeResponsesDir);
    Diag := TStringList.Create;
    Diag.Add('diag ok');
    Diag.SaveToFile(BridgeDir + '\diag_run.txt');
    Diag.Free;
    DbgMark('start');
    BridgeForm.Show;
    DbgMark('shown');
End;