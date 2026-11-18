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
import csv
import io
from bot import execute, CONFIG
from runtime_paths import ROOT
from PIL import Image, ImageTk, ImageOps
import media_library
from tutorial import STEPS

BG='#140d23';PANEL='#241732';FG='#fff2fb';MUTED='#c4aecf';CYAN='#69e8e0';VIOLET='#ef5ca9'

def status_summary(raw):
    data=json.loads(raw)
    active=[x.get('name','Output') for x in data.get('outputs',[]) if any(x.get(k) is True for k in ('active','streaming','outputActive'))]
    if data.get('main_stream_active'):active.insert(0,'Main OBS')
    return {'output':', '.join(active) if active else 'All streams stopped','scene':data.get('scene') or 'No scene','portrait':data.get('vertical_scene') or 'No scene','live':bool(active)}

def open_obs():
    candidates=[Path(os.environ.get('ProgramFiles','C:/Program Files'))/'obs-studio/bin/64bit/obs64.exe',Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'obs-studio/bin/64bit/obs64.exe']
    path=next((p for p in candidates if p.exists()),None)
    if not path:raise RuntimeError('OBS was not found. Use Setup to download the official installer.')
    if os.name=='nt':
        result=subprocess.run(['tasklist','/FI','IMAGENAME eq obs64.exe','/FO','CSV','/NH'],capture_output=True,text=True,timeout=5,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode!=0:raise RuntimeError('Could not check OBS activity. Open OBS manually, then click Check connection.')
        if any(row and row[0].casefold()=='obs64.exe' for row in csv.reader(io.StringIO(result.stdout))):
            return 'OBS is already running. Restore it from the taskbar if needed, then click Check connection.'
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
        media=media_library.preferences(CONFIG)
        self.media_mode=tk.StringVar(value=media['mode']);self.music_on=tk.BooleanVar(value=media['music_enabled']);self.countdown_on=tk.BooleanVar(value=media['countdown_enabled'])
        self.media_photos={};self.media_status=tk.StringVar(value='Your files stay on this computer. Apply changes with all OBS outputs stopped.')
        self.scroll_canvases={}
        self.tutorial_index=0;self.tutorial_done=set()
        try:self.tutorial_done={n for n in json.loads((ROOT/'tutorial-progress.json').read_text()) if isinstance(n,int) and 0<=n<len(STEPS)}
        except (OSError,ValueError,TypeError):pass
        self.tutorial_checked=tk.BooleanVar(value=False)
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
        style.configure('TButton',padding=(13,10),background='#3b264e',foreground=FG,borderwidth=0)
        style.map('TButton',background=[('active','#58356f'),('disabled','#241b30')],foreground=[('disabled','#917d9d')])
        style.configure('Primary.TButton',background=VIOLET)
        style.map('Primary.TButton',background=[('active','#ff8ac8')],foreground=[('!disabled','#1b0b20')])
        style.configure('Safe.TButton',background='#87384b')
        style.map('Safe.TButton',background=[('active','#aa4c62')])
        style.configure('TNotebook',background=BG,borderwidth=0,lightcolor=BG,darkcolor=BG,bordercolor=BG)
        style.configure('TNotebook.Tab',padding=(16,10),background=PANEL)
        style.map('TNotebook.Tab',background=[('selected','#4b2855')],foreground=[('selected','#ff9dcf')])
        style.configure('TCombobox',fieldbackground=PANEL,foreground=FG,padding=7)
        style.map('TCombobox',fieldbackground=[('readonly',PANEL)],foreground=[('readonly',FG)])
        style.configure('TRadiobutton',background=BG,foreground=FG,padding=5)
        style.configure('TCheckbutton',background=BG,foreground=FG,padding=5)

    def label(self,parent,text=None,variable=None,style=None,**kw):
        label=ttk.Label(parent,text=text,textvariable=variable,style=style or 'TLabel',**kw);return label

    def button(self,parent,text,action,style='TButton',**pack):
        b=ttk.Button(parent,text=text,command=action,style=style);b.pack(**pack);self.buttons.append(b)
        if text in ('SAFE SCREEN','Stop all streams'):self.emergency.append(b)
        return b

    def build(self):
        outer=ttk.Frame(self,padding=24);outer.pack(fill='both',expand=True)
        self.hero=tk.Canvas(outer,height=135,bg=BG,highlightthickness=0);self.hero.pack(fill='x',pady=(0,14))
        self.hero_background=Image.open(ROOT/'assets/vice-sunset-background.png').convert('RGB')
        self.hero_logo=Image.open(ROOT/'assets/revonwheels-logo.png').convert('RGBA')
        self.icon_photo=ImageTk.PhotoImage(self.hero_logo.resize((128,128),Image.Resampling.LANCZOS));self.iconphoto(True,self.icon_photo)
        self.hero.bind('<Configure>',self.draw_hero)
        b=ttk.Button(self.hero,text='Open OBS',command=lambda:self.run('Open OBS',function=open_obs));b.place(relx=1.0,x=-14,y=14,anchor='ne');self.buttons.append(b)
        cards=ttk.Frame(outer);cards.pack(fill='x',pady=(0,18))
        for index,(title,var) in enumerate([('OBS CONNECTION',self.connection_text),('STREAM OUTPUTS',self.output_text),('LANDSCAPE SCENE',self.scene_text),('PORTRAIT SCENE',self.portrait_text)]):
            cards.columnconfigure(index,weight=1,uniform='cards')
            card=ttk.Frame(cards,style='Card.TFrame',padding=13);card.grid(row=0,column=index,sticky='nsew',padx=(0,8))
            self.label(card,title,style='CardTitle.TLabel').pack(anchor='w')
            self.label(card,variable=var,style='Card.TLabel',wraplength=225).pack(anchor='w',pady=(8,0))
        notebook=ttk.Notebook(outer,height=380);notebook.pack(fill='both',expand=True)
        control=ttk.Frame(notebook,padding=20);setup_tab=ttk.Frame(notebook);history=ttk.Frame(notebook,padding=10)
        guide=ttk.Frame(notebook,padding=16);media_tab=ttk.Frame(notebook)
        setup=self.scrollable(setup_tab);media_page=self.scrollable(media_tab)
        notebook.add(control,text='Stream desk');notebook.add(guide,text='Prerequisite guide');notebook.add(media_tab,text='Artwork & music');notebook.add(setup_tab,text='Setup tools');notebook.add(history,text='Activity')
        self.notebook=notebook;self.guide_page=guide;self.media_page=media_tab
        self.bind_all('<MouseWheel>',self.scroll_tab,add='+')
        self.build_guide(guide);self.build_media(media_page)
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
        self.label(setup,'Quick setup tools',font=('Segoe UI Semibold',17)).pack(anchor='w')
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
        if not (ROOT/'config.json').exists():notebook.select(guide)

    def draw_hero(self,event):
        width=event.width
        if width<100:return
        self.hero.delete('art')
        self.hero_photo=ImageTk.PhotoImage(ImageOps.fit(self.hero_background,(width,135),centering=(.5,.82)))
        self.logo_photo=ImageTk.PhotoImage(self.hero_logo.resize((114,114),Image.Resampling.LANCZOS))
        self.hero.create_image(0,0,image=self.hero_photo,anchor='nw',tags='art')
        self.hero.create_image(18,10,image=self.logo_photo,anchor='nw',tags='art')
        self.hero.create_text(150,34,text='REVONWHEELS  /  STREAM DESK',fill='#ffb6da',font=('Segoe UI Semibold',10),anchor='w',tags='art')
        self.hero.create_text(150,71,text='YOUR STREAM. YOUR CITY.',fill='white',font=('Segoe UI Semibold',23),anchor='w',tags='art')
        self.hero.create_text(150,105,text='Sunset colours. Full control. Ready for your next session.',fill='#efd3ee',font=('Segoe UI',10),anchor='w',tags='art')

    def scrollable(self,tab):
        scrollbar=ttk.Scrollbar(tab,orient='vertical');scrollbar.pack(side='right',fill='y')
        canvas=tk.Canvas(tab,bg=BG,highlightthickness=0,yscrollcommand=scrollbar.set);canvas.pack(side='left',fill='both',expand=True);scrollbar.config(command=canvas.yview)
        inner=ttk.Frame(canvas,padding=16);window=canvas.create_window(0,0,window=inner,anchor='nw')
        inner.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(window,width=e.width))
        self.scroll_canvases[str(tab)]=canvas
        return inner

    def scroll_tab(self,event):
        canvas=self.scroll_canvases.get(self.notebook.select())
        if canvas:canvas.yview_scroll(-int(event.delta/120),'units')

    def build_guide(self,parent):
        self.label(parent,'Before your first stream',font=('Segoe UI Semibold',18)).pack(anchor='w')
        self.guide_progress=tk.StringVar();self.label(parent,variable=self.guide_progress,style='Muted.TLabel').pack(anchor='w',pady=(3,12))
        layout=ttk.Frame(parent);layout.pack(fill='both',expand=True)
        left=ttk.Frame(layout);left.pack(side='left',fill='y',padx=(0,20))
        self.guide_list=tk.Listbox(left,width=26,height=8,bg=PANEL,fg=FG,selectbackground='#804571',selectforeground='white',font=('Segoe UI',11),relief='flat',highlightthickness=0,exportselection=False,activestyle='none')
        self.guide_list.pack(fill='y',expand=True);self.guide_list.bind('<<ListboxSelect>>',self.select_guide_step)
        right=ttk.Frame(layout);right.pack(side='left',fill='both',expand=True)
        right.columnconfigure(0,weight=1);right.rowconfigure(2,weight=1)
        self.guide_title=tk.StringVar();self.guide_subtitle=tk.StringVar()
        self.label(right,variable=self.guide_title,font=('Segoe UI Semibold',16)).grid(row=0,column=0,sticky='w')
        self.label(right,variable=self.guide_subtitle,style='Muted.TLabel').grid(row=1,column=0,sticky='w',pady=(3,10))
        reading=ttk.Frame(right);reading.grid(row=2,column=0,sticky='nsew')
        text_scroll=ttk.Scrollbar(reading);text_scroll.pack(side='right',fill='y')
        self.guide_text=tk.Text(reading,height=7,bg=BG,fg=FG,font=('Segoe UI',11),wrap='word',relief='flat',highlightthickness=0,spacing1=2,spacing3=5,yscrollcommand=text_scroll.set)
        self.guide_text.pack(side='left',fill='both',expand=True);text_scroll.config(command=self.guide_text.yview)
        self.guide_actions=ttk.Frame(right);self.guide_actions.grid(row=3,column=0,sticky='ew',pady=8)
        ttk.Checkbutton(right,text='I completed this step',variable=self.tutorial_checked,command=self.mark_step).grid(row=4,column=0,sticky='w')
        nav=ttk.Frame(right);nav.grid(row=5,column=0,sticky='ew',pady=(7,0))
        self.button(nav,'← Previous',lambda:self.show_step(max(0,self.tutorial_index-1)),side='left')
        self.button(nav,'Next step →',lambda:self.show_step(min(len(STEPS)-1,self.tutorial_index+1)),'Primary.TButton',side='right')
        self.show_step(0)

    def select_guide_step(self,event=None):
        selected=self.guide_list.curselection()
        if selected:self.show_step(selected[0])

    def show_step(self,index):
        self.tutorial_index=index
        title,subtitle,body,actions=STEPS[index]
        self.guide_title.set(f'{index+1:02d}  {title}');self.guide_subtitle.set(subtitle)
        self.guide_text.configure(state='normal');self.guide_text.delete('1.0','end');self.guide_text.insert('1.0',body);self.guide_text.configure(state='disabled')
        for child in self.guide_actions.winfo_children():child.destroy()
        for label,command in actions:
            action=(lambda p=command.split()[-1]:self.install(p)) if command.startswith('dependencies install') else (lambda c=command:self.run(c))
            self.button(self.guide_actions,label,action,side='left',padx=(0,8))
        if index==5:self.button(self.guide_actions,'Choose artwork & music',lambda:self.notebook.select(self.media_page),'Primary.TButton',side='left')
        self.tutorial_checked.set(index in self.tutorial_done)
        self.guide_progress.set(f'{len(self.tutorial_done)} / {len(STEPS)} steps marked complete · your checklist, not an automatic readiness guarantee')
        self.guide_list.delete(0,'end')
        for n,(name,*_) in enumerate(STEPS):self.guide_list.insert('end',('✓ ' if n in self.tutorial_done else f'{n+1:02d} ')+name)
        self.guide_list.selection_set(index)

    def mark_step(self):
        if self.tutorial_checked.get():self.tutorial_done.add(self.tutorial_index)
        else:self.tutorial_done.discard(self.tutorial_index)
        (ROOT/'tutorial-progress.json').write_text(json.dumps(sorted(self.tutorial_done)))
        self.show_step(self.tutorial_index)

    def build_media(self,parent):
        self.label(parent,'Make the stream yours',font=('Segoe UI Semibold',18)).pack(anchor='w')
        self.label(parent,'Use the included RevOnWheels pack, or pick local files. Unset custom slots keep their included asset.',style='Muted.TLabel',wraplength=950).pack(anchor='w',pady=(3,9))
        choices=ttk.Frame(parent);choices.pack(fill='x',pady=(0,10))
        for text,value in [('Included theme','included'),('My images & music','custom')]:
            ttk.Radiobutton(choices,text=text,value=value,variable=self.media_mode,command=self.save_media).pack(side='left',padx=(0,18))
        pictures=ttk.Frame(parent);pictures.pack(fill='x')
        self.media_previews={};self.media_names={}
        for index,key in enumerate(('landscape','portrait','brb')):
            pictures.columnconfigure(index,weight=1,uniform='art')
            card=ttk.Frame(pictures,style='Card.TFrame',padding=10);card.grid(row=0,column=index,sticky='nsew',padx=(0,10))
            self.label(card,media_library.LABELS[key],style='Card.TLabel').pack(anchor='w')
            preview=ttk.Label(card,style='Card.TLabel');preview.pack(pady=6);self.media_previews[key]=preview
            name=tk.StringVar();self.media_names[key]=name;self.label(card,variable=name,style='CardTitle.TLabel',wraplength=260).pack(anchor='w')
            row=ttk.Frame(card,style='Card.TFrame');row.pack(fill='x',pady=(6,0))
            self.button(row,'Choose image',lambda k=key:self.choose_media(k),side='left',padx=(0,6))
            self.button(row,'Reset',lambda k=key:self.reset_media(k),side='left')
        row=ttk.Frame(parent);row.pack(fill='x',pady=(12,7))
        self.music_name=tk.StringVar();self.label(row,variable=self.music_name,wraplength=540).pack(side='left',expand=True,fill='x')
        self.button(row,'Choose music',lambda:self.choose_media('music'),side='left',padx=(0,8))
        self.button(row,'Reset music',lambda:self.reset_media('music'),side='left')
        row=ttk.Frame(parent);row.pack(fill='x')
        ttk.Checkbutton(row,text='Loop music on banner scenes',variable=self.music_on,command=self.save_media).pack(side='left',padx=(0,18))
        ttk.Checkbutton(row,text='Show GTA countdown (review sample date first)',variable=self.countdown_on,command=self.save_media).pack(side='left')
        row=ttk.Frame(parent);row.pack(fill='x',pady=(8,0))
        self.button(row,'Apply media to OBS',self.apply_media,'Primary.TButton',side='left',padx=(0,12))
        self.label(row,variable=self.media_status,style='Muted.TLabel',wraplength=700).pack(side='left')
        self.refresh_media()

    def media_preferences(self):
        pref=media_library.preferences(CONFIG)
        pref.update(mode=self.media_mode.get(),music_enabled=self.music_on.get(),countdown_enabled=self.countdown_on.get())
        return pref

    def save_media(self):
        if self.busy:
            self.media_status.set('Wait for the current action before changing media.');return
        media_library.save(CONFIG,self.media_preferences())
        self.media_status.set('Saved locally. Stop outputs, then Apply media to OBS.');self.refresh_media()

    def choose_media(self,key):
        types=[('Images','*.png *.jpg *.jpeg *.webp')] if key in media_library.IMAGE_KEYS else [('Audio','*.wav *.mp3 *.ogg *.flac *.m4a')]
        source=filedialog.askopenfilename(parent=self,title='Choose '+media_library.LABELS[key],filetypes=types)
        if not source:return
        try:
            path=media_library.import_file(key,source)
            pref=self.media_preferences();pref['files'][key]=path;pref['mode']='custom'
            media_library.save(CONFIG,pref);self.media_mode.set('custom');self.refresh_media()
            self.media_status.set('File copied locally. Apply media to OBS when outputs are stopped.')
        except Exception as exc:messagebox.showerror('Could not use that file',str(exc),parent=self)

    def reset_media(self,key):
        pref=self.media_preferences();pref['files'].pop(key,None);media_library.save(CONFIG,pref);self.refresh_media()
        self.media_status.set('Slot reset to its included asset. Apply changes to update OBS.')

    def refresh_media(self):
        from setup_obs import FILES
        files=media_library.resolve(CONFIG,FILES)
        for key,label in self.media_previews.items():
            try:
                with Image.open(files[key]) as image:thumb=ImageOps.contain(image.convert('RGB'),(250,92))
                self.media_photos[key]=ImageTk.PhotoImage(thumb);label.configure(image=self.media_photos[key],text='')
            except (OSError,ValueError):label.configure(image='',text='Choose an available image')
            self.media_names[key].set(Path(files[key]).name)
        self.music_name.set('Music: '+Path(files['music']).name)

    def apply_media(self):
        self.save_media()
        self.run('Apply media',function=lambda:media_library.apply(CONFIG))

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
        self.buttons=[b for b in self.buttons if b.winfo_exists()]
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
                    self.buttons=[b for b in self.buttons if b.winfo_exists()]
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
