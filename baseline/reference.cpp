// Driver only. Algorithms are included from prepare.py's frozen-source extraction.
#include <QApplication>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QFile>
#include <QFileInfo>
#include <QCryptographicHash>
#include <QSysInfo>
#include <QThread>
#include <QProcess>
#include <QFontDatabase>
#include <QTextStream>
#include <numeric>
#include <algorithm>
#include <stdexcept>
#include <omp.h>
#include "telemetry.h"
#include "headers/cpp_interface/videocapturelist.h"
#include "headers/qml_interface/frameprocessing_qml.h"
#include "headers/qml_interface/imageconverter_qml.h"
#include "headers/qml_interface/imagecomposer_qml.h"
#include "headers/qml_interface/renderer_qml.h"
#include "headers/qml_interface/exporter_qml.h"
#include "headers/qml_models/framerateoptionsmodel.h"

static const char* sourceSha="a0b4563a076e336863f743ec92c1ee8221f5aba6";
struct BaselineProbe {
    static FrameProcessing& engine(FrameProcessingQML& a){return a._frame_processing;}
    static const cv::Mat& mask(FrameProcessing& a,int v){return a._difference_frames[v];}
    static double contribution(FrameProcessing& a,int v){
        const auto& ring=a._frame_diff_lists.at(v);
        if(ring.empty())return 0;
        return ring.at((a._current_framecount_list.at(v)+ring.size()-1)%ring.size());
    }
    static size_t retained(const TearModel&a){return a._tear_list.size();}
    static QJsonArray tears(const std::vector<TearData>&t){QJsonArray out;
        for(const auto&x:t){auto p=x.get_indices();out.append(QJsonArray{int(x.get_video_index()),int(std::get<0>(p)),int(std::get<1>(p))});}return out;}
    static QJsonArray retainedTears(const TearModel&a){return tears(a._tear_list);}
    static QJsonObject images(const RendererQML&a){qint64 bytes=0;int nonnull=0;
        for(const auto&i:a._cached_images){bytes+=i.sizeInBytes();if(!i.isNull())++nonnull;}
        return {{"slots",int(a._cached_images.size())},{"nonnull",nonnull},{"logical_bytes",double(bytes)}};
    }
};
static QByteArray read(const QString&p){QFile f(p);if(!f.open(QIODevice::ReadOnly))throw std::runtime_error("Cannot read "+p.toStdString());return f.readAll();}
static void write(const QString&p,const QByteArray&b){QFile f(p);if(!f.open(QIODevice::WriteOnly|QIODevice::NewOnly)||f.write(b)!=b.size())throw std::runtime_error("Cannot write new "+p.toStdString());}
static void json(const QString&p,const QJsonObject&o){write(p,QJsonDocument(o).toJson());}
static QString hash(const QByteArray&b){return QCryptographicHash::hash(b,QCryptographicHash::Sha256).toHex();}
static QJsonObject dump(const QString&root,const QString&name,const cv::Mat&m){
    QByteArray bytes;for(int y=0;y<m.rows;++y)bytes.append(reinterpret_cast<const char*>(m.ptr(y)),m.cols*int(m.elemSize()));
    write(root+'/'+name,bytes);return {{"file",name},{"sha256",hash(bytes)},{"bytes",bytes.size()}};
}
static QJsonArray doubles(const std::vector<double>&a){QJsonArray b;for(auto v:a)b.append(v);return b;}
static QJsonArray integers(const std::vector<int>&a){QJsonArray b;for(auto v:a)b.append(v);return b;}
static QJsonObject runtime(const QJsonObject&c){
    QJsonObject o{{"source_sha",sourceSha},{"os",QSysInfo::prettyProductName()},
        {"kernel",QSysInfo::kernelVersion()},{"architecture",QSysInfo::currentCpuArchitecture()},
        {"logical_processors_qt",QThread::idealThreadCount()},{"compiler",__VERSION__},
        {"qt",qVersion()},{"opencv",CV_VERSION},{"opencv_threads",cv::getNumThreads()},
        {"opencv_build",QString::fromStdString(cv::getBuildInformation())},
        {"omp_max_threads",omp_get_max_threads()},{"omp_num_procs",omp_get_num_procs()},
        {"omp_dynamic",omp_get_dynamic()},{"omp_nested",omp_get_nested()},
        {"omp_max_active_levels",omp_get_max_active_levels()},{"case_settings",c},
        {"preview",false},{"driver","offscreen synchronous original stages; no QML event-loop pacing"}};
    int actual=0;
    #pragma omp parallel
    {
        #pragma omp single
        actual=omp_get_num_threads();
    }
    o["omp_probe_team_size"]=actual;
    QJsonObject env;for(const auto*n:{"OMP_NUM_THREADS","OMP_DYNAMIC","OMP_NESTED","OMP_MAX_ACTIVE_LEVELS","OMP_THREAD_LIMIT","QT_QPA_PLATFORM"})env[n]=QString::fromLocal8Bit(qgetenv(n));o["environment"]=env;
    QProcess p;
    p.start("powershell",{"-NoProfile","-Command","Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors | ConvertTo-Json -Compress"});
    if(p.waitForFinished(10000)&&p.exitCode()==0){QJsonDocument d=QJsonDocument::fromJson(p.readAllStandardOutput());
        o["cpu"]=d.isArray()?QJsonValue(d.array()):QJsonValue(d.object());}
    else o["cpu"]=QJsonObject{{"unavailable",true},{"reason","Win32_Processor query failed"}};
    #ifdef BASELINE_PROFILE
    o["profile_compiled"]=true;
    #else
    o["profile_compiled"]=false;
    #endif
    #ifdef BASELINE_OBSERVE
    o["observer_compiled"]=true;
    #else
    o["observer_compiled"]=false;
    #endif
    return o;
}
static void timings(const QString&path){
    #ifdef BASELINE_PROFILE
    QJsonObject stages;for(int i=0;i<baseline::stage_count;++i){const auto&m=baseline::measurements()[i];
        stages[baseline::names[i]]=QJsonObject{{"nanoseconds",double(m.ns.load())},{"calls",double(m.calls.load())}};}
    json(path,{{"clock","steady_clock"},{"units","nanoseconds"},{"stages",stages},
        {"trace_enabled",baseline::observing()},{"warning","Nested/parallel stage sums are not additive wall time; trace runs are not performance benchmarks"}});
    #else
    Q_UNUSED(path)
    #endif
}

int main(int argc,char**argv){
    QApplication app(argc,argv);
    QLocale::setDefault(QLocale::c());
    QFontDatabase::addApplicationFont(":/fonts/FjallaOne-Regular.ttf");
    const QStringList args=app.arguments();
    auto arg=[&](const QString&key,const QString&fallback=QString()){
        int i=args.indexOf(key);return i>=0&&i+1<args.size()?args[i+1]:fallback;};
    try{
        const QString output=arg("--output");if(output.isEmpty()||QFileInfo::exists(output))throw std::runtime_error("--output must be a new directory");
        QDir().mkpath(output+"/semantic");const QString semantic=output+"/semantic";
        const bool trace=!args.contains("--no-trace");
        #ifndef BASELINE_OBSERVE
        if(trace)throw std::runtime_error("This executable has observation compiled out; use --no-trace");
        #endif
        baseline::observing()=trace;
        cv::setNumThreads(arg("--opencv-threads","1").toInt());
        QJsonObject c;const QString fixture=arg("--fixtures"), id=arg("--case"), videoPath=arg("--video");
        if(!videoPath.isEmpty()){
            c={{"id","decoded_video"},{"pipeline",true},{"csv",true},{"fps",60},{"threshold",0},{"dismiss",10}};
        }else{
            const auto manifest=QJsonDocument::fromJson(read(fixture)).object();
            for(auto x:manifest["cases"].toArray())if(x.toObject()["id"].toString()==id)c=x.toObject();
            if(c.isEmpty())throw std::runtime_error("Unknown fixture case");
        }
        VideoCaptureList capture(3);QJsonObject config=runtime(c);
        QList<QVariant> names;
        int count=c["streams"].toArray().size();
        if(!videoPath.isEmpty()){
            names.append(videoPath);capture.open_videos(names);count=1;
            auto vc=capture.get_videocapture_by_index(0);
            if(!vc.isOpened())throw std::runtime_error("VideoCapture could not open input");
            c["fps"]=capture.get_recorded_framerate(0);
            config["video"]=QJsonObject{{"backend",QString::fromStdString(vc.getBackendName())},
                {"fps",vc.get(cv::CAP_PROP_FPS)},{"width",vc.get(cv::CAP_PROP_FRAME_WIDTH)},
                {"height",vc.get(cv::CAP_PROP_FRAME_HEIGHT)},{"reported_frames",vc.get(cv::CAP_PROP_FRAME_COUNT)},
                {"fourcc_numeric",vc.get(cv::CAP_PROP_FOURCC)},{"codec_pixel_format_numeric",vc.get(cv::CAP_PROP_CODEC_PIXEL_FORMAT)},
                {"decoded_layout","actual Mat type and row-packed bytes captured per frame; codec pixel format -1 means unavailable"}};
        }else for(int i=0;i<count;++i)names.append(QString("fixture_%1.raw").arg(i));
        config["case_settings"]=c;json(output+"/runtime.json",config);
        auto fps=std::make_shared<FramerateModel>();auto ft=std::make_shared<FrametimeModel>();
        auto fo=std::make_shared<QList<FramerateOptions>>();auto to=std::make_shared<QList<TearOptions>>();
        auto res=std::make_shared<ResolutionsModel>();auto general=std::make_shared<GeneralOptionsModel>();
        auto ex=std::make_shared<ExportOptionsModel>();auto fmt=std::make_shared<ImageFormatModel>();
        FramerateOptionsModel fm(fps,fo,res);TearOptionsModel tm(to);
        for(int i=0;i<3;++i){(*fo)[i].enabled=i<count;(*fo)[i].fps_plot_color.setColor("#00ff00");
            (*fo)[i].pixel_difference.setValue(c["threshold"].toInt());(*to)[i].dismiss_tear_percentage.setValue(c["dismiss"].toDouble(10));}
        general->setData(general->index(0),c["draw_tears"].toBool(true),GeneralOptionsModel::EnableTearsValueRole);
        general->setData(general->index(0),c["center"].toBool(false),GeneralOptionsModel::EnableFrametimeCenteringValueRole);
        auto tears=std::make_shared<TearModel>(to,res,general);
        auto fp=std::make_shared<FrameratePlot>(fps,fo,res,general);
        auto ftp=std::make_shared<FrametimePlot>(ft,fo,res,general);
        FrameProcessingQML processing(fps,ft,fo,to,general,tears);
        ImageConverterQML converter;ImageComposerQML composer(res);
        RendererQML renderer(fo,general,ex,fp,ftp,tears,res);
        ExporterQML exporter(ex,fmt,fps,ft);
        ex->setData(ex->index(0),semantic,ExportOptionsModel::ExportDirectoryValueRole);
        ex->setData(ex->index(0),c["csv"].toBool(),ExportOptionsModel::ExportCSVValueRole);
        ex->setData(ex->index(0),c["images"].toBool(),ExportOptionsModel::ImagesequencePrefixEnabledRole);
        exporter.updateVideoCount(names);exporter.setIsExporting(true);
        QList<quint8> rates;for(int i=0;i<count;++i)rates.append(static_cast<quint8>(std::ceil(c["fps"].toDouble())));
        processing.resetState(rates);
        QList<cv::Mat> forwarded;QList<QImage> images;QImage composed,rendered;
        QObject::connect(&processing,&FrameProcessingQML::framesReady,[&](const QList<cv::Mat>&a){forwarded=a;});
        QObject::connect(&converter,&ImageConverterQML::imagesReady,[&](const QList<QImage>&a){images=a;});
        QObject::connect(&composer,&ImageComposerQML::imageReady,[&](const QImage&a){composed=a;});
        QObject::connect(&renderer,&RendererQML::imageReady,[&](const QImage&a){rendered=a;});
        QJsonArray records;int frame=0,compared=0,duplicates=0;bool first=true;
        const auto streams=c["streams"].toArray();int frames=0;
        if(videoPath.isEmpty()){frames=count?streams[0].toArray().size():0;
            for(auto s:streams)frames=std::min(frames,s.toArray().size());}
        const int limit=arg("--limit","1000000").toInt();
        {
        BASE_SCOPE(run_clock,end_to_end);
        while(frame<limit && (!videoPath.isEmpty() || frame<frames)){
            BASE_SCOPE(frame_clock,total_frame);
            QList<cv::Mat> input;
            if(!videoPath.isEmpty()){
                if(!capture.populate_next_frames())break;
                input=capture.frame_list;
            }else{
                for(int v=0;v<count;++v){auto f=streams[v].toArray()[frame].toObject();
                    const auto data=read(QFileInfo(fixture).dir().filePath(f["path"].toString()));
                    if(hash(data)!=f["sha256"].toString())throw std::runtime_error("Fixture SHA mismatch");
                    int w=c["width"].toInt(),h=c["height"].toInt();
                    if(data.size()!=w*h*3)throw std::runtime_error("Fixture size mismatch");
                    cv::Mat owned(h,w+(c["padded"].toBool()?7:0),CV_8UC3,cv::Scalar::all(99));
                    cv::Mat roi=owned(cv::Rect(0,0,w,h));for(int y=0;y<h;++y)memcpy(roi.ptr(y),data.constData()+y*w*3,w*3);
                    input.append(roi);
                }
            }
            if(c.contains("reset_at")&&frame==c["reset_at"].toInt()){processing.resetState(rates);first=true;}
            auto changes=c["threshold_at"].toObject();if(changes.contains(QString::number(frame)))
                for(int v=0;v<count;++v)(*fo)[v].pixel_difference.setValue(changes[QString::number(frame)].toInt());
            if(trace)for(auto&o:baseline::observations())o=baseline::Observation();
            processing.processFrames(input);
            QJsonObject rec{{"source_index",frame},{"comparison_available",!first}};QJsonArray videos;
            for(int v=0;v<count;++v){
                if(!first){++compared;if(BaselineProbe::contribution(BaselineProbe::engine(processing),v)==0)++duplicates;}
                if(trace){
                    const QString prefix=QString("f%1-v%2-").arg(frame,6,10,QChar('0')).arg(v);
                    QJsonObject r{{"video",v},{"width",input[v].cols},{"height",input[v].rows},{"mat_type",input[v].type()},
                        {"input",dump(semantic,prefix+"input.bgr",input[v])},{"threshold",int((*fo)[v].pixel_difference.value())},
                        {"fps",fps->get_framerate_at(v)},{"frametime_ms",ft->get_frametime_at(v)}};
                    if(!first){const auto&o=baseline::observations()[v];
                        r["gray_a"]=dump(semantic,prefix+"gray-a.bin",o.gray_a);r["gray_b"]=dump(semantic,prefix+"gray-b.bin",o.gray_b);
                        r["mask"]=dump(semantic,prefix+"mask.bin",BaselineProbe::mask(BaselineProbe::engine(processing),v));
                    }
                    videos.append(r);
                }
            }
            // Filled below via BaselineProbe; no extra analysis call is made.
            if(trace){for(int v=0;v<count;++v)if(!first){auto r=videos[v].toObject();const auto&o=baseline::observations()[v];
                r["per_row_counts"]=integers(o.counts);r["changed_pixels"]=std::accumulate(o.counts.begin(),o.counts.end(),0);
                r["row_fraction"]=doubles(o.fractions);r["branch"]=QString::fromStdString(o.branch);
                r["contribution"]=BaselineProbe::contribution(BaselineProbe::engine(processing),v);
                r["duplicate"]=BaselineProbe::contribution(BaselineProbe::engine(processing),v)==0;videos[v]=r;}
                rec["videos"]=videos;rec["tears"]=BaselineProbe::tears(BaselineProbe::engine(processing).get_tear_indices());
                rec["retained_before_render"]=BaselineProbe::retainedTears(*tears);}
            if(c["pipeline"].toBool()){
                converter.processFrames(forwarded);composer.processImages(images);renderer.processImage(composed);
                exporter.setIsExporting(!(c["preview_first"].toBool()&&frame==0));exporter.processImage(rendered);
                if(c.contains("redraw_at")&&frame==c["redraw_at"].toInt()){renderer.redraw();exporter.processImage(rendered);}
            }
            if(trace){rec["retained_after_render"]=int(BaselineProbe::retained(*tears));rec["image_queue"]=BaselineProbe::images(renderer);records.append(rec);}
            first=false;++frame;
        }
        exporter.finishExporting();
        }
        if(!videoPath.isEmpty()){
            json(output+"/decode-smoke.json",{{"decoded_frames",frame},{"limit",limit}});
            if(frame==0)throw std::runtime_error("Decode smoke test decoded zero frames");
        }
        QJsonObject summary{{"source_sha",sourceSha},{"case",c["id"]},{"submitted_batches",frame},
            {"compared_pairs",compared},{"duplicate_pairs",duplicates},{"nonduplicate_pairs",compared-duplicates},
            {"export_names_after_finish",exporter._file_item_list.size()},{"export_active_videos_after_finish",exporter._active_video_count}};
        if(!videoPath.isEmpty()){summary["decoded_frames"]=frame;QJsonArray counts;for(auto n:capture.frame_count_list)counts.append(double(n));summary["successful_reads"]=counts;
            capture.restart_state();QJsonArray reset;for(auto n:capture.frame_count_list)reset.append(double(n));summary["read_counters_after_restart"]=reset;}
        if(trace){summary["frames"]=records;json(semantic+"/trace.json",summary);}
        else json(output+"/summary.json",summary);
        timings(output+"/timings.json");
        if(c["reexport"].toBool()){exporter.setIsExporting(true);exporter.processImage(rendered);}
        return 0;
    }catch(const std::exception&e){QTextStream(stderr)<<e.what()<<'\n';return 2;}
}
