"""RevOnWheels Windows desktop controller. No stream starts on app launch."""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import shutil
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import webbrowser
from bot import execute, CONFIG
from runtime_paths import ROOT

BG='#0c101b';PANEL='#151d2d';FG='#edf3ff';MUTED='#a4b3cc';CYAN='#59e1dc';VIOLET='#9568ff'

def status_summary(raw):
    data=json.loads(raw)
    active=[x.get('name','Output') for x in data.get('outputs',[]) if any(x.get(k) is True for k in ('active','streaming','outputActive'))]
    if data.get('main_stream_active'):active.insert(0,'Main OBS')
    return {'output':', '.join(active) if active else 'All streams stopped','scene':data.get('scene') or 'No scene','portrait':data.get('vertical_scene') or 'No scene','live':bool(active)}

def open_obs():
    candidates=[Path(os.environ.get('ProgramFiles','C:/Program Files'))/'obs-studio/bin/64bit/obs64.exe',Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'obs-studio/bin/64bit/obs64.exe']
    path=next((p for p in candidates if p.exists()),None)
    if not path:raise RuntimeError('OBS was not found. Use Setup to download the official installer.')
    subprocess.Popen([str(path)],cwd=str(path.parent))
    return 'OBS launch requested. Complete any startup prompt, then click Check connection.'

def import_setup(source):
    source=Path(source)
    config=json.loads((source/'config.json').read_text(encoding='utf-8-sig'))
    if not isinstance(config.get('scenes'),dict) or not config.get('canvas'):raise ValueError('This is not a bot configuration folder.')
    if source.resolve()==ROOT.resolve():return 'This folder is already in use.'
    backup=ROOT/'backups'/('before-desktop-import-'+str(time.time_ns()));backup.mkdir(parents=True,exist_ok=True)
    for name in ('config.json','setup-manifest.json','safe-state.json'):
        target=ROOT/name
        if target.exists():shutil.copy2(target,backup/name)
        if (source/name).exists():shutil.copy2(source/name,target)
    CONFIG.clear();CONFIG.update(config)
    return 'Existing local bot settings imported. Click Check connection.'

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('RevOnWheels · Stream Desk')
        self.geometry('1120x800');self.minsize(940,720);self.configure(bg=BG)
        self.events=queue.Queue();self.busy=False;self.pending=0;self.buttons=[];self.emergency=[];self.closing=False
        self.connection_text=tk.StringVar(value='Checking OBS…')
        self.output_text=tk.StringVar(value='Waiting for connection')
        self.scene_text=tk.StringVar(value='—');self.portrait_text=tk.StringVar(value='—')
        self.message=tk.StringVar(value='Prepare your setup, check picture and sound, then choose Go Live.')
        self.device=tk.StringVar();self.devices=[]
        self.style_ui();self.build()
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.after(100,self.drain);self.after(300,lambda:self.run('status',quiet=True))
        self.after(6000,self.poll)

    def style_ui(self):
        style=ttk.Style(self);style.theme_use('clam')
        style.configure('.',font=('Segoe UI',10),background=BG,foreground=FG)
        style.configure('TFrame',background=BG)
        style.configure('Card.TFrame',background=PANEL)
        style.configure('TLabel',background=BG,foreground=FG)
        style.configure('Muted.TLabel',foreground=MUTED)
        style.configure('Title.TLabel',font=('Segoe UI Semibold',25))
        style.configure('Card.TLabel',background=PANEL)
        style.configure('CardTitle.TLabel',background=PANEL,foreground=MUTED,font=('Segoe UI',9))
        style.configure('TButton',padding=(13,10),background='#24324b',foreground=FG,borderwidth=0)
        style.map('TButton',background=[('active','#354c70'),('disabled','#1b2435')],foreground=[('disabled','#667590')])
        style.configure('Primary.TButton',background=VIOLET)
        style.map('Primary.TButton',background=[('active','#ad87ff')])
        style.configure('Safe.TButton',background='#87384b')
        style.map('Safe.TButton',background=[('active','#aa4c62')])
        style.configure('TNotebook',background=BG,borderwidth=0)
        style.configure('TNotebook.Tab',padding=(22,10),background=PANEL)
        style.map('TNotebook.Tab',background=[('selected','#283951')],foreground=[('selected',CYAN)])
        style.configure('TCombobox',fieldbackground=PANEL,foreground=FG,padding=7)

    def label(self,parent,text=None,variable=None,style=None,**kw):
        label=ttk.Label(parent,text=text,textvariable=variable,style=style or 'TLabel',**kw);return label

    def button(self,parent,text,action,style='TButton',**pack):
        b=ttk.Button(parent,text=text,command=action,style=style);b.pack(**pack);self.buttons.append(b)
        if text in ('SAFE SCREEN','Stop all streams'):self.emergency.append(b)
        return b

    def build(self):
        outer=ttk.Frame(self,padding=24);outer.pack(fill='both',expand=True)
        header=ttk.Frame(outer);header.pack(fill='x')
        self.label(header,'REVONWHEELS',style='Muted.TLabel').pack(anchor='w')
        self.label(header,'Your stream. Ready to roll.',style='Title.TLabel').pack(side='left',pady=(5,18))
        self.button(header,'Open OBS',lambda:self.run('Open OBS',function=open_obs),side='right')
        cards=ttk.Frame(outer);cards.pack(fill='x',pady=(0,18))
        for index,(title,var) in enumerate([('OBS CONNECTION',self.connection_text),('STREAM OUTPUTS',self.output_text),('LANDSCAPE SCENE',self.scene_text),('PORTRAIT SCENE',self.portrait_text)]):
            cards.columnconfigure(index,weight=1,uniform='cards')
            card=ttk.Frame(cards,style='Card.TFrame',padding=13);card.grid(row=0,column=index,sticky='nsew',padx=(0,8))
            self.label(card,title,style='CardTitle.TLabel').pack(anchor='w')
            self.label(card,variable=var,style='Card.TLabel',wraplength=225).pack(anchor='w',pady=(8,0))
        notebook=ttk.Notebook(outer);notebook.pack(fill='both',expand=True)
        control=ttk.Frame(notebook,padding=20);setup=ttk.Frame(notebook,padding=20);history=ttk.Frame(notebook,padding=10)
        notebook.add(control,text='Stream controls');notebook.add(setup,text='First-time setup');notebook.add(history,text='Activity')
        self.label(control,'1   Prepare your picture',font=('Segoe UI Semibold',15)).pack(anchor='w')
        row=ttk.Frame(control);row.pack(fill='x',pady=(12,20))
        for title,cmd in [('Starting Soon','prepare'),('Gameplay','gameplay'),('Be Right Back','brb')]:self.button(row,title,lambda c=cmd:self.run(c),side='left',padx=(0,10))
        self.label(control,'2   Control your stream',font=('Segoe UI Semibold',15)).pack(anchor='w')
        row=ttk.Frame(control);row.pack(fill='x',pady=(12,18))
        self.button(row,'Go Live · YouTube',lambda:self.go_live('live youtube'),'Primary.TButton',side='left',padx=(0,10))
        self.button(row,'Go Live · All platforms',lambda:self.go_live('live all'),'Primary.TButton',side='left',padx=(0,10))
        self.button(row,'Stop all streams',lambda:self.run('stop'),'Safe.TButton',side='left')
        row=ttk.Frame(control);row.pack(fill='x',pady=(0,16))
        self.button(row,'SAFE SCREEN',lambda:self.run('safe'),'Safe.TButton',side='left',padx=(0,10))
        self.button(row,'Resume',lambda:self.run('resume'),side='left',padx=(0,10))
        for title,cmd in [('Mic off','mic off'),('Mic on','mic on'),('Camera off','camera off')]:self.button(row,title,lambda c=cmd:self.run(c),side='left',padx=(0,10))
        self.label(control,'Safe Screen is a manual cover. It does not detect or blur content automatically.',style='Muted.TLabel',wraplength=880).pack(anchor='w',pady=(0,16))
        row=ttk.Frame(control);row.pack(fill='x')
        for title,cmd in [('Check connection','doctor'),('Refresh status','status'),('Auto quality','quality auto'),('Save highlight','highlight')]:self.button(row,title,lambda c=cmd:self.run(c),side='left',padx=(0,10))
        self.label(control,'Go Live uses your configured accounts and visibility. Confirm reception in each platform dashboard.',style='Muted.TLabel',wraplength=880).pack(anchor='w',pady=16)
        self.label(setup,'Get ready in four steps',font=('Segoe UI Semibold',17)).pack(anchor='w')
        self.label(setup,'OBS and the capture card stay separate from this app. Your accounts and keys stay in OBS.',style='Muted.TLabel',wraplength=880).pack(anchor='w',pady=(6,12))
        self.label(setup,'1. Install OBS and Aitum if missing. Close OBS before running an installer.').pack(anchor='w')
        row=ttk.Frame(setup);row.pack(fill='x',pady=(8,12))
        for name in ('obs','aitum'):
            self.button(row,'Download '+name.upper(),lambda n=name:self.run('dependencies download '+n),side='left',padx=(0,8))
            self.button(row,'Install '+name.upper(),lambda n=name:self.install(n),side='left',padx=(0,14))
        self.label(setup,'2. In OBS, enable authenticated WebSocket. Add an Aitum canvas named YouTube Vertical (720 × 1280).',wraplength=900).pack(anchor='w',pady=(0,12))
        self.label(setup,'3. Stop every OBS/Aitum output, then build your scenes. Webcam stays off.').pack(anchor='w')
        row=ttk.Frame(setup);row.pack(fill='x',pady=(8,12))
        for title,cmd in [('Prepare PS5 setup','setup auto ps5'),('Prepare PC GTA setup','setup auto pc'),('Validate setup','setup check')]:self.button(row,title,lambda c=cmd:self.run(c),side='left',padx=(0,10))
        self.label(setup,'4. Connect PS5 → HDMI capture → USB laptop. If needed, select the capture card below.').pack(anchor='w')
        row=ttk.Frame(setup);row.pack(fill='x',pady=8)
        self.combo=ttk.Combobox(row,textvariable=self.device,state='readonly',width=35);self.combo.pack(side='left',padx=(0,10))
        self.button(row,'Find devices',lambda:self.run('devices'),side='left',padx=(0,10))
        self.button(row,'Use this card',self.select_device,side='left')
        self.label(setup,'Set PS5 HDMI/HDCP on the console. Check actual picture and game audio before broadcasting.',style='Muted.TLabel',wraplength=880).pack(anchor='w',pady=8)
        row=ttk.Frame(setup);row.pack(fill='x',pady=8)
        self.button(row,'Open local app files',lambda:os.startfile(str(ROOT)),side='left',padx=(0,10))
        self.button(row,'Import existing bot',self.import_existing,side='left',padx=(0,10))
        self.button(row,'YouTube Studio',lambda:webbrowser.open('https://studio.youtube.com'),side='left')
        scroll=ttk.Scrollbar(history);scroll.pack(side='right',fill='y')
        self.log=tk.Text(history,bg=PANEL,fg=FG,insertbackground=FG,relief='flat',wrap='word',font=('Consolas',10),padx=14,pady=14,yscrollcommand=scroll.set,state='disabled');self.log.pack(fill='both',expand=True);scroll.config(command=self.log.yview)
        self.label(outer,variable=self.message,style='Muted.TLabel',wraplength=1000).pack(anchor='w',pady=(12,0))

    def install(self,package):
        if messagebox.askokcancel('Open installer','Close OBS first. This opens the verified '+package.upper()+' installer. Complete Windows prompts yourself. Continue?',parent=self):self.run('dependencies install '+package)

    def import_existing(self):
        folder=filedialog.askdirectory(title='Choose your existing RevOnWheels-Bot folder',parent=self)
        if folder and messagebox.askokcancel('Import local setup','Use settings from this bot folder? Current app settings are backed up locally.',parent=self):
            self.run('Import setup',function=lambda:import_setup(folder))

    def go_live(self,command):
        destinations='main OBS + YouTube Vertical' if command=='live youtube' else 'main OBS + configured Aitum outputs'
        if messagebox.askyesno('Start configured streams?',f'Start {destinations}?\n\nExisting account and visibility settings will be used. The broadcast may be public. YouTube may still need Go live in Studio.',parent=self):self.run(command)

    def select_device(self):
        index=self.combo.current()
        if index<0:messagebox.showinfo('Choose a capture card','Click Find devices, then select your HDMI capture card.',parent=self);return
        self.run('capture ps5 '+str(index+1))

    def run(self,command,quiet=False,function=None):
        if self.busy and command not in ('safe','stop'):return
        self.pending+=1;self.busy=True
        self.message.set('Working: '+command+'…')
        for b in self.buttons:
            if b not in self.emergency:b.state(['disabled'])
        self.combo.configure(state='disabled')
        def work():
            try:
                result=(function or (lambda:execute(command)))()
                devices=None
                if command=='devices':devices=json.loads((ROOT/'capture-devices.json').read_text())
                self.events.put((command,result,None,quiet,devices))
            except Exception as exc:self.events.put((command,None,str(exc),quiet,None))
        threading.Thread(target=work,daemon=True).start()

    def drain(self):
        try:
            while True:
                command,result,error,quiet,devices=self.events.get_nowait()
                self.pending-=1;self.busy=self.pending>0
                if not self.busy:
                    for b in self.buttons:b.state(['!disabled'])
                    self.combo.configure(state='readonly')
                if error:
                    self.message.set(error)
                    if command=='status':self.connection_text.set('Not connected');self.output_text.set('Unknown · check OBS')
                    self.append('ERROR · '+command+'\n'+error)
                    if not quiet:messagebox.showerror('Action needs attention',error,parent=self)
                else:
                    if command=='status':
                        status=status_summary(result);self.connection_text.set('Connected');self.output_text.set(status['output']);self.scene_text.set(status['scene']);self.portrait_text.set(status['portrait'])
                    if devices is not None:
                        self.devices=devices;self.combo['values']=[x['itemName'] for x in devices]
                        if devices:self.combo.current(0)
                    if not quiet:self.append(command+'\n'+str(result))
                    self.message.set('OBS status refreshed.' if quiet else str(result).split('\n')[0])
                    if command!='status' and not command.startswith('dependencies'):self.after(150,lambda:self.run('status',quiet=True))
        except queue.Empty:pass
        if not self.closing:self.after(100,self.drain)

    def append(self,text):
        self.log.configure(state='normal');self.log.insert('end',text+'\n\n');self.log.see('end');self.log.configure(state='disabled')

    def poll(self):
        if not self.busy:self.run('status',quiet=True)
        if not self.closing:self.after(6000,self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo('Action in progress','Wait for the current action to finish before closing.',parent=self);return
        self.closing=True;self.destroy()

if __name__=='__main__':App().mainloop()
